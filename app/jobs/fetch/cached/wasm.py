import asyncio
import json
from typing import List, Optional

from api.aionode.connector import ThorConnector
from api.aionode.wasm import WasmCodeManager, WasmCodeInfo, WasmContract
from jobs.fetch.cached.base import CachedDataSource
from lib.date_utils import DAY
from lib.db import DB
from models.wasm import WasmCodeStats, WasmContractStats, WasmContractEntry


class WasmCache(CachedDataSource[WasmContractStats]):
    """
    Fetches and caches aggregated WASM data:
      - all deployed code variants (metadata)
      - all contract instances per code ID with their labels
      - totals

    In-memory cache + optional Redis persistence (survives process restarts).
    Default cache period: 1 day.
    """

    REDIS_KEY = 'WasmCache:stats'
    REDIS_LABELS_HASH = 'WasmCache:labels'  # no TTL — labels are immutable
    INTER_REQUEST_SLEEP: float = 0.05
    # max parallel contract-info requests
    LABEL_FETCH_CONCURRENCY: int = 10

    def __init__(self, thor_connector: ThorConnector,
                 db: Optional[DB] = None,
                 cache_period: float = DAY,
                 retry_times: int = 3):
        super().__init__(cache_period=cache_period, retry_times=retry_times,
                         retry_exponential_growth_factor=2.0)
        self.code_manager = WasmCodeManager(thor_connector)
        self._connector = thor_connector
        self.db = db

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _save_to_redis(self, stats: WasmContractStats) -> None:
        try:
            r = await self.db.get_redis()
            payload = json.dumps(stats.to_dict())
            await r.setex(self.REDIS_KEY, int(self.cache_period), payload)
            self.logger.info(f"WasmCache: saved to Redis (TTL={int(self.cache_period)}s).")
        except Exception as exc:
            self.logger.warning(f"WasmCache: failed to save to Redis: {exc}")

    async def _load_from_redis(self) -> Optional[WasmContractStats]:
        try:
            r = await self.db.get_redis()
            raw = await r.get(self.REDIS_KEY)
            if raw:
                stats = WasmContractStats.from_dict(json.loads(raw))
                self.logger.info(
                    f"WasmCache: restored from Redis — "
                    f"{stats.total_codes} code(s), {stats.total_contracts} contract(s)."
                )
                return stats
        except Exception as exc:
            self.logger.warning(f"WasmCache: failed to load from Redis: {exc}")
        return None

    # ------------------------------------------------------------------
    # Label fetching
    # ------------------------------------------------------------------

    async def _persist_labels_to_hash(self, entries: List[WasmContractEntry]) -> None:
        """Bulk-write address→label pairs into the Redis hash (no TTL)."""
        if not entries or self.db is None:
            return
        try:
            r = await self.db.get_redis()
            mapping = {e.address: e.label for e in entries}
            await r.hset(self.REDIS_LABELS_HASH, mapping=mapping)
            self.logger.debug(f"Persisted {len(mapping)} label(s) to Redis hash '{self.REDIS_LABELS_HASH}'.")
        except Exception as exc:
            self.logger.warning(f"WasmCache: failed to persist labels hash: {exc}")

    async def _fetch_labels(self, addresses: List[str],
                            semaphore: asyncio.Semaphore) -> List[WasmContractEntry]:
        total = len(addresses)
        done = 0

        async def fetch_one(address: str) -> WasmContractEntry:
            nonlocal done
            async with semaphore:
                try:
                    info = await WasmContract(self._connector, address).get_contract_info()
                    label = info.label
                except Exception as exc:
                    self.logger.warning(f"Could not fetch label for {address}: {exc}")
                    label = ''
                finally:
                    done += 1
                    self.logger.debug(f"  labels [{done}/{total}]  {address}  -> {label!r}")
                return WasmContractEntry(address=address, label=label)

        return list(await asyncio.gather(*[fetch_one(a) for a in addresses]))

    # ------------------------------------------------------------------
    # Core load
    # ------------------------------------------------------------------

    async def _load(self) -> WasmContractStats:
        # 1. Try Redis before hitting the network
        if self.db is not None:
            cached = await self._load_from_redis()
            if cached is not None:
                return cached

        # 2. Network fetch
        codes: List[WasmCodeInfo] = await self.code_manager.get_all_codes()
        self.logger.info(f"Fetched {len(codes)} WASM code(s); loading contracts + labels...")

        semaphore = asyncio.Semaphore(self.LABEL_FETCH_CONCURRENCY)
        code_stats: List[WasmCodeStats] = []
        total_codes = len(codes)

        for idx, code_info in enumerate(codes, start=1):
            self.logger.debug(f"code [{idx}/{total_codes}] id={code_info.code_id} ...")
            try:
                addresses = await self.code_manager.get_all_contracts_of_code(code_info.code_id)
                self.logger.debug(
                    f"  code_id={code_info.code_id}: {len(addresses)} contract(s) found, fetching labels..."
                )
                entries = await self._fetch_labels(addresses, semaphore)
            except Exception as exc:
                self.logger.warning(
                    f"Could not fetch contracts for code_id={code_info.code_id}: {exc}"
                )
                entries = []

            self.logger.debug(
                f"  code_id={code_info.code_id}: done — {len(entries)} entry(ies) loaded."
            )
            code_stats.append(WasmCodeStats(code_info=code_info, contracts=entries))
            await self._persist_labels_to_hash(entries)

            if self.INTER_REQUEST_SLEEP > 0:
                await asyncio.sleep(self.INTER_REQUEST_SLEEP)

        stats = WasmContractStats(codes=code_stats)
        self.logger.info(
            f"WasmCache loaded from network: {stats.total_codes} code(s), "
            f"{stats.total_contracts} contract(s) total."
        )

        # 3. Persist to Redis for next startup
        if self.db is not None:
            await self._save_to_redis(stats)

        return stats

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def get_label(self, address: str) -> str:
        """
        Return the on-chain label for a contract address.

        Lookup order:
          1. In-memory stats (if already loaded)
          2. Redis hash  WasmCache:labels  (fast, no full-stats load needed)
          3. Live network fetch  →  stored in Redis hash for future calls
        """
        # 1. In-memory
        if self._cache is not None:
            label = self._cache.find_label(address)
            if label is not None:
                self.logger.debug(f"get_label: in-memory hit for {address!r}")
                return label

        # 2. Redis hash
        if self.db is not None:
            try:
                r = await self.db.get_redis()
                label = await r.hget(self.REDIS_LABELS_HASH, address)
                if label is not None:
                    self.logger.debug(f"get_label: Redis hash hit for {address!r} -> {label!r}")
                    return label
            except Exception as exc:
                self.logger.warning(f"get_label: Redis lookup failed: {exc}")

        # 3. Network fetch
        self.logger.debug(f"get_label: fetching from network for {address!r}")
        try:
            info = await WasmContract(self._connector, address).get_contract_info()
            label = info.label
        except Exception as exc:
            self.logger.warning(f"get_label: could not fetch info for {address!r}: {exc}")
            return ''

        # Store in Redis hash so next call is instant
        if self.db is not None:
            try:
                r = await self.db.get_redis()
                await r.hset(self.REDIS_LABELS_HASH, address, label)
                self.logger.debug(f"get_label: stored {address!r} -> {label!r} in Redis hash.")
            except Exception as exc:
                self.logger.warning(f"get_label: failed to store in Redis hash: {exc}")

        return label

