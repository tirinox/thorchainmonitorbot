import asyncio
import json
from typing import List, Optional, Dict, Tuple

from api.aionode.connector import ThorConnector
from api.aionode.wasm import WasmCodeManager, WasmCodeInfo, WasmContract
from jobs.fetch.cached.base import CachedDataSource
from lib.date_utils import DAY, now_ts
from lib.db import DB
from models.wasm import WasmCodeStats, WasmContractStats, WasmContractEntry, NewWasmDeployments


class WasmCache(CachedDataSource[WasmContractStats]):
    """
    Fetches and caches aggregated WASM data:
      - all deployed code variants (metadata)
      - all contract instances per code ID with their labels and creation block
      - totals

    In-memory cache + optional Redis persistence (survives process restarts).
    Default cache period: 1 day.

    A contract's label and creation block never change, so they are kept in Redis without TTL
    (REDIS_CONTRACTS_HASH) and a refresh only asks the node for contracts it has not seen yet.
    """

    REDIS_KEY = 'WasmCache:stats'
    REDIS_LABELS_HASH = 'WasmCache:labels'          # no TTL — labels are immutable
    REDIS_CODE_FIRST_SEEN_HASH = 'WasmCache:code_first_seen'  # no TTL — ever-growing log
    REDIS_CONTRACTS_HASH = 'WasmCache:contracts'    # no TTL — address -> {label, block_height}
    INTER_REQUEST_SLEEP: float = 0.05
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
    # Redis helpers — main stats blob
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
    # Redis helpers — labels hash
    # ------------------------------------------------------------------

    async def _persist_labels_to_hash(self, entries: List[WasmContractEntry]) -> None:
        """Bulk-write address→label pairs into the Redis hash (no TTL)."""
        if not entries or self.db is None:
            return
        try:
            r = await self.db.get_redis()
            mapping = {e.address: e.label for e in entries}
            await r.hset(self.REDIS_LABELS_HASH, mapping=mapping)
            self.logger.debug(
                f"Persisted {len(mapping)} label(s) to Redis hash '{self.REDIS_LABELS_HASH}'."
            )
        except Exception as exc:
            self.logger.warning(f"WasmCache: failed to persist labels hash: {exc}")

    # ------------------------------------------------------------------
    # Redis helpers — known contracts hash
    # ------------------------------------------------------------------

    async def _load_known_contracts(self) -> Dict[str, WasmContractEntry]:
        """All contracts fetched before: address → entry with its label and creation block."""
        if self.db is None:
            return {}
        try:
            r = await self.db.get_redis()
            raw = await r.hgetall(self.REDIS_CONTRACTS_HASH)
            return {
                address: WasmContractEntry.from_dict(json.loads(payload))
                for address, payload in raw.items()
            }
        except Exception as exc:
            self.logger.warning(f"WasmCache: failed to load known contracts: {exc}")
            return {}

    async def _persist_known_contracts(self, entries: List[WasmContractEntry]) -> None:
        if not entries or self.db is None:
            return
        try:
            r = await self.db.get_redis()
            mapping = {e.address: json.dumps(e.to_dict()) for e in entries}
            await r.hset(self.REDIS_CONTRACTS_HASH, mapping=mapping)
        except Exception as exc:
            self.logger.warning(f"WasmCache: failed to persist known contracts: {exc}")

    # ------------------------------------------------------------------
    # Redis helpers — code first_seen hash
    # ------------------------------------------------------------------

    async def _record_new_codes(self, codes: List[WasmCodeInfo]) -> Dict[int, float]:
        """
        For each code, return its first_seen timestamp.
        New code IDs (not yet in Redis) are recorded with now_ts() and persisted.
        Returns Dict[code_id → first_seen_ts].
        """
        if self.db is None:
            ts = now_ts()
            return {c.code_id: ts for c in codes}

        try:
            r = await self.db.get_redis()
            existing = await r.hgetall(self.REDIS_CODE_FIRST_SEEN_HASH)
            existing = {int(k): float(v) for k, v in existing.items()}
        except Exception as exc:
            self.logger.warning(f"WasmCache: failed to load code first_seen: {exc}")
            existing = {}

        ts = now_ts()
        result: Dict[int, float] = {}
        new_entries: Dict[str, str] = {}

        for code in codes:
            if code.code_id in existing:
                result[code.code_id] = existing[code.code_id]
            else:
                result[code.code_id] = ts
                new_entries[str(code.code_id)] = str(ts)
                self.logger.debug(f"New code_id={code.code_id} first seen at ts={ts:.0f}.")

        if new_entries:
            try:
                r = await self.db.get_redis()
                await r.hset(self.REDIS_CODE_FIRST_SEEN_HASH, mapping=new_entries)
                self.logger.debug(
                    f"Recorded {len(new_entries)} new code first_seen entry(ies) in Redis."
                )
            except Exception as exc:
                self.logger.warning(f"WasmCache: failed to persist code first_seen: {exc}")

        return result

    # ------------------------------------------------------------------
    # Label + block_height fetching
    # ------------------------------------------------------------------

    async def _fetch_labels(self, addresses: List[str],
                            semaphore: asyncio.Semaphore) -> Tuple[List[WasmContractEntry], List[WasmContractEntry]]:
        """
        Returns (entries for all addresses, entries fetched successfully).
        A failed fetch still yields an empty entry, but must not be remembered, so it is retried next time.
        """
        total = len(addresses)
        done = 0
        fetched: List[WasmContractEntry] = []

        async def fetch_one(address: str) -> WasmContractEntry:
            nonlocal done
            async with semaphore:
                try:
                    info = await WasmContract(self._connector, address).get_contract_info()
                    label = info.label
                    block_height = info.created.block_height if info.created else 0
                    ok = True
                except Exception as exc:
                    self.logger.warning(f"Could not fetch label for {address}: {exc}")
                    label = ''
                    block_height = 0
                    ok = False
                finally:
                    done += 1
                    self.logger.debug(
                        f"  labels [{done}/{total}]  {address}"
                        f"  block={block_height}  -> {label!r}"
                    )
                entry = WasmContractEntry(address=address, label=label, block_height=block_height)
                if ok:
                    fetched.append(entry)
                return entry

        entries = list(await asyncio.gather(*[fetch_one(a) for a in addresses]))
        return entries, fetched

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

        # Resolve first_seen timestamps for all codes in one batch
        first_seen_map = await self._record_new_codes(codes)

        known = await self._load_known_contracts()
        label_semaphore = asyncio.Semaphore(self.LABEL_FETCH_CONCURRENCY)
        list_semaphore = asyncio.Semaphore(self.LABEL_FETCH_CONCURRENCY)
        total_codes = len(codes)
        new_contracts = 0

        async def load_code(idx: int, code_info: WasmCodeInfo) -> WasmCodeStats:
            nonlocal new_contracts
            try:
                async with list_semaphore:
                    self.logger.debug(f"code [{idx}/{total_codes}] id={code_info.code_id} ...")
                    addresses = await self.code_manager.get_all_contracts_of_code(code_info.code_id)
                    if self.INTER_REQUEST_SLEEP > 0:
                        await asyncio.sleep(self.INTER_REQUEST_SLEEP)
                unknown = [a for a in addresses if a not in known]
                self.logger.debug(
                    f"  code_id={code_info.code_id}: {len(addresses)} contract(s) found,"
                    f" {len(unknown)} new, fetching their labels..."
                )
                fetched_entries, fetched_ok = await self._fetch_labels(unknown, label_semaphore)
                fetched_map = {e.address: e for e in fetched_entries}
                entries = [known[a] if a in known else fetched_map[a] for a in addresses]
                new_contracts += len(unknown)
            except Exception as exc:
                self.logger.warning(
                    f"Could not fetch contracts for code_id={code_info.code_id}: {exc}"
                )
                entries, fetched_ok = [], []

            self.logger.debug(
                f"  code_id={code_info.code_id}: done — {len(entries)} entry(ies) loaded."
            )
            await self._persist_labels_to_hash(fetched_ok)
            await self._persist_known_contracts(fetched_ok)
            return WasmCodeStats(
                code_info=code_info,
                contracts=entries,
                first_seen_ts=first_seen_map.get(code_info.code_id, 0.0),
            )

        code_stats: List[WasmCodeStats] = list(await asyncio.gather(
            *[load_code(idx, code_info) for idx, code_info in enumerate(codes, start=1)]
        ))

        stats = WasmContractStats(codes=code_stats)
        self.logger.info(
            f"WasmCache loaded from network: {stats.total_codes} code(s), "
            f"{stats.total_contracts} contract(s) total, {new_contracts} of them fetched as new."
        )

        # 3. Persist full snapshot to Redis
        if self.db is not None:
            await self._save_to_redis(stats)

        return stats

    # ------------------------------------------------------------------
    # Convenience — label lookup
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

        if self.db is not None:
            try:
                r = await self.db.get_redis()
                await r.hset(self.REDIS_LABELS_HASH, address, label)
                self.logger.debug(f"get_label: stored {address!r} -> {label!r} in Redis hash.")
            except Exception as exc:
                self.logger.warning(f"get_label: failed to store in Redis hash: {exc}")

        return label

    # ------------------------------------------------------------------
    # Convenience — new deployments
    # ------------------------------------------------------------------

    async def count_new_deployments(
        self,
        days: float = 7.0,
        last_block_cache=None,
    ) -> NewWasmDeployments:
        """
        Return new codes and contracts deployed in the last *days* days.

        - New codes:     code IDs whose first_seen_ts falls within the window.
        - New contracts: contracts whose creation block_height falls within the window
                         (requires last_block_cache to convert time → block height;
                          without it every contract with block_height > 0 is included).
        """
        stats = await self.get()
        min_ts = now_ts() - days * DAY

        new_codes = stats.new_codes_since_ts(min_ts)

        if last_block_cache is not None:
            min_block = await last_block_cache.get_thor_block_time_ago(days * DAY)
            new_contracts = stats.new_contracts_since_block(min_block or 0)
        else:
            self.logger.warning(
                "count_new_deployments: no last_block_cache provided; "
                "filtering contracts by block_height > 0 only."
            )
            new_contracts = stats.new_contracts_since_block(1)

        self.logger.debug(
            f"count_new_deployments({days}d): "
            f"{len(new_codes)} new code(s), {len(new_contracts)} new contract(s)."
        )
        return NewWasmDeployments(new_codes=new_codes, new_contracts=new_contracts, days=days)
