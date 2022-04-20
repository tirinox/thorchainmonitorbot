import json
from typing import Optional

from aioredis import Redis

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.jobs.fetch.pool_price import PoolInfoFetcherMidgard
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.pool_info import PoolInfoMap, PoolDetailHolder


class BestPoolsNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        cooldown = parse_timespan_to_seconds(deps.cfg.as_str('best_pools.cooldown', '5h'))
        self._cooldown = Cooldown(self.deps.db, 'BestPools', cooldown)
        self._fetcher: Optional[PoolInfoFetcherMidgard] = None
        self.last_pool_detail: PoolDetailHolder = PoolDetailHolder({}, {})
        self.n_pools = deps.cfg.as_int('best_pools.num_of_top_pools', 5)

    DB_KEY_PREVIOUS_STATS = 'PreviousPoolsState'

    async def _write_previous_data(self, raw_pool_data):
        if not raw_pool_data:
            self.logger.warning('attempt to save empty data')
            return
        r: Redis = self.deps.db.redis
        await r.set(self.DB_KEY_PREVIOUS_STATS, json.dumps(raw_pool_data))

    async def _get_previous_data(self) -> PoolInfoMap:
        r: Redis = self.deps.db.redis
        raw_data = await r.get(self.DB_KEY_PREVIOUS_STATS)
        if raw_data is None:
            return {}
        data = json.loads(raw_data)
        if not data:
            return {}
        result = self._fetcher.parser.parse_pool_info(data)
        if not isinstance(result, dict):
            return {}
        else:
            return result

    async def on_data(self, sender: PoolInfoFetcherMidgard, data: PoolInfoMap):
        self._fetcher = sender

        # await self._cooldown.clear()  # fixme (debug)

        prev = await self._get_previous_data()
        self.last_pool_detail = PoolDetailHolder(curr=data, prev=prev)

        if await self._cooldown.can_do():
            await self._notify(self.last_pool_detail)
            await self._write_previous_data(sender.last_raw_result)
            await self._cooldown.do()

    async def _notify(self, pd: PoolDetailHolder):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_best_pools,
            pd, self.n_pools)
