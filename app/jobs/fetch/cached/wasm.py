import asyncio
import json
from typing import List, Optional

from api.aionode.connector import ThorConnector
from api.aionode.wasm import WasmCodeManager, WasmCodeInfo
from jobs.fetch.cached.base import CachedDataSource
from lib.date_utils import HOUR
from lib.db import DB
from models.wasm import WasmCodeStats, WasmContractStats


class WasmCache(CachedDataSource[WasmContractStats]):
    """
    Fetches and caches aggregated WASM data:
      - all deployed code variants (metadata)
      - number of contract instances per code ID
      - totals

    In-memory cache + optional Redis persistence (survives process restarts).
    Default cache period: 1 hour.
    """

    REDIS_KEY = 'WasmCache:stats'
    INTER_REQUEST_SLEEP: float = 0.05

    def __init__(self, thor_connector: ThorConnector,
                 db: Optional[DB] = None,
                 cache_period: float = HOUR,
                 retry_times: int = 3):
        super().__init__(cache_period=cache_period, retry_times=retry_times,
                         retry_exponential_growth_factor=2.0)
        self.code_manager = WasmCodeManager(thor_connector)
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
        self.logger.info(f"Fetched {len(codes)} WASM code(s); loading contract counts…")

        code_stats: List[WasmCodeStats] = []
        for code_info in codes:
            try:
                all_addresses = await self.code_manager.get_all_contracts_of_code(code_info.code_id)
                count = len(all_addresses)
            except Exception as exc:
                self.logger.warning(
                    f"Could not fetch contracts for code_id={code_info.code_id}: {exc}"
                )
                count = 0

            code_stats.append(WasmCodeStats(code_info=code_info, contract_count=count))

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

