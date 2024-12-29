import json
from typing import Optional

from redis.asyncio import Redis

from comm.localization.languages import Language
from jobs.fetch.pool_price import PoolInfoFetcherMidgard
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.pool_info import PoolInfoMap, EventPools
from notify.channel import BoardMessage


class BestPoolsNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()

        self.deps = deps
        cooldown = parse_timespan_to_seconds(deps.cfg.as_str('best_pools.cooldown', '5h'))
        self._cooldown = Cooldown(self.deps.db, 'BestPools', cooldown)
        self._fetcher: Optional[PoolInfoFetcherMidgard] = None
        self.last_pool_detail = EventPools({}, {})
        self.n_pools = deps.cfg.as_int('best_pools.num_of_top_pools', 5)
        self.income_intervals = 7
        self.income_period = 'day'

    DB_KEY_PREVIOUS_STATS = 'PoolInfo:PreviousPoolsState'

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

        # + 1 is due to the Midgard's bug that responds the last day with zero-fields
        earnings = await self.deps.midgard_connector.query_earnings(count=self.income_intervals + 1,
                                                                    interval=self.income_period)

        usd_per_rune = self.deps.price_holder.calculate_rune_price_here(data)
        self.last_pool_detail = EventPools(data, prev, earnings, usd_per_rune=usd_per_rune)

        if await self._cooldown.can_do():
            await self._cooldown.do()
            await self._notify(self.last_pool_detail)
            await self._write_previous_data(sender.last_raw_result)

    async def _notify(self, pd: EventPools):
        await self.pass_data_to_listeners(pd)

    async def _debug_twitter(self):
        notifier: BestPoolsNotifier = self.deps.best_pools_notifier
        loc = self.deps.loc_man[Language.ENGLISH_TWITTER]
        text = loc.notification_text_best_pools(notifier.last_pool_detail, notifier.n_pools)
        await self.deps.twitter_bot.send_message('', BoardMessage(text))
