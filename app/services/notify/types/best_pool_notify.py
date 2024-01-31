import json
from typing import Optional

from redis.asyncio import Redis

from localization.languages import Language
from localization.manager import BaseLocalization
from services.jobs.fetch.pool_price import PoolInfoFetcherMidgard
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfoMap, PoolMapPair
from services.notify.channel import BoardMessage


class BestPoolsNotifier(INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()

        self.deps = deps
        cooldown = parse_timespan_to_seconds(deps.cfg.as_str('best_pools.cooldown', '5h'))
        self._cooldown = Cooldown(self.deps.db, 'BestPools', cooldown)
        self._fetcher: Optional[PoolInfoFetcherMidgard] = None
        self.last_pool_detail = PoolMapPair({}, {})
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
        # We use PoolInfoFetcherMidgard because it has "last_raw_result" and asset prices
        self._fetcher = sender

        prev = await self._get_previous_data()
        self.last_pool_detail = PoolMapPair(curr=data, prev=prev)

        if await self._cooldown.can_do():
            await self._cooldown.do()
            await self._notify(self.last_pool_detail)
            await self._write_previous_data(sender.last_raw_result)

    async def _notify(self, pd: PoolMapPair):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_best_pools,
            pd, self.n_pools)

    async def _debug_twitter(self):
        notifier: BestPoolsNotifier = self.deps.best_pools_notifier
        loc = self.deps.loc_man[Language.ENGLISH_TWITTER]
        text = loc.notification_text_best_pools(notifier.last_pool_detail, notifier.n_pools)
        await self.deps.twitter_bot.send_message('', BoardMessage(text))
