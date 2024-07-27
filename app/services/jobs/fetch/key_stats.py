import asyncio
import datetime

from aionode.types import thor_to_float
from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.flipside.flipside import FlipSideConnector, FSList
from services.jobs.fetch.flipside.urls import *
from services.jobs.fetch.pool_price import PoolFetcher
from services.jobs.user_counter import UserCounterMiddleware
from services.jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.flipside import FSAffiliateCollectors, FSFees, FSSwapCount, FSLockedValue, FSSwapVolume, \
    FSSwapRoutes, AlertKeyStats, KeyStats
from services.models.vol_n import TxCountStats


# Swap history: https://midgard.ninerealms.com/v2/history/swaps?interval=week&count=2
# Earnings history: https://midgard.ninerealms.com/v2/history/earnings?interval=week&count=2


class KeyStatsFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.key_metrics.fetch_period)
        super().__init__(deps, sleep_period)
        self._fs = FlipSideConnector(deps.session, deps.cfg.flipside.api_key)
        self.tally_days_period = deps.cfg.as_int('key_metrics.tally_period_days', 7)

        # x3 days (this week + previous week + spare days)
        self.trim_max_days = deps.cfg.as_int('key_metrics.trim_max_days', self.tally_days_period * 3)

    async def fetch(self) -> AlertKeyStats:
        # Find block height a week ago
        previous_block = self.deps.last_block_store.block_time_ago(self.tally_days_period * DAY)

        if previous_block < 0:
            raise ValueError(f'Previous block is negative {previous_block}!')

        # Load pool data for BTC/ETH value in the pools
        pf: PoolFetcher = self.deps.pool_fetcher
        curr_pools, prev_pools = await asyncio.gather(
            pf.load_pools(),
            pf.load_pools(height=previous_block)
        )

        curr_pools = pf.convert_pool_list_to_dict(list(curr_pools.values()))
        prev_pools = pf.convert_pool_list_to_dict(list(prev_pools.values()))

        # TC's locked asset value
        prev_lock, curr_lock = await asyncio.gather(
            self.get_lock_value(self.tally_days_period),
            self.get_lock_value()
        )

        # Swapper count
        user_counter: UserCounterMiddleware = self.deps.user_counter
        user_stats = await user_counter.get_main_stats()

        # Swap volumes (trade, synth, normal)
        prev_swap_vol_dict, curr_swap_vol_dict = await self.get_swap_volume_stats()
        swap_count = await self.get_swap_number_stats()

        # Combined THORChain stats from Flipside Crypto
        fs_series = await self.get_flipside_series()

        # Swap routes
        routes = await self._fs.request_daily_series_v2(FS_LATEST_SWAP_PATH_URL, FSSwapRoutes)
        routes = routes.most_recent

        # Done. Construct the resulting event
        return AlertKeyStats(
            fs_series,
            routes=routes,
            days=self.tally_days_period,
            current=KeyStats(
                curr_pools,
                curr_lock,
                curr_swap_vol_dict,
                swap_count.curr,
                swapper_count=user_stats.wau,
            ),
            previous=KeyStats(
                prev_pools,
                prev_lock,
                prev_swap_vol_dict,
                swap_count.prev,
                swapper_count=user_stats.wau_prev_weak
            )
        )

    async def get_flipside_series(self):
        loaders = [
            (FS_LATEST_EARNINGS_URL, FSFees),
            (FS_LATEST_SWAP_COUNT_URL, FSSwapCount),
            (FS_LATEST_LOCKED_RUNE_URL, FSLockedValue),
            (FS_LATEST_SWAP_VOL_URL, FSSwapVolume),
            (FS_LATEST_SWAP_AFF_FEE_URL, FSAffiliateCollectors),
        ]

        # Actual API requests
        data_chunks = await asyncio.gather(
            *[self._fs.request_daily_series_v2(url, klass) for url, klass in loaders]
        )

        # Merge data streams
        return FSList.combine(*data_chunks)

    async def get_lock_value(self, days_ago=0) -> FSLockedValue:
        height = self.deps.last_block_store.block_time_ago(days_ago * DAY)
        pools = await self.deps.pool_fetcher.load_pools(height=height)
        price_holder = self.deps.price_holder.clone().update(pools)

        total_pooled_rune = price_holder.total_pooled_value_rune
        total_pooled_usd = price_holder.total_pooled_value_usd

        nodes = await self.deps.thor_connector.query_node_accounts()
        total_bonded_rune = sum([thor_to_float(node.bond) for node in nodes])
        total_bonded_usd = total_bonded_rune * price_holder.usd_per_rune

        date = datetime.datetime.now() - datetime.timedelta(days=days_ago)

        return FSLockedValue(
            date,
            total_pooled_rune,
            total_pooled_usd,
            total_bonded_rune,
            total_bonded_usd,
            total_value_locked=total_pooled_rune + total_bonded_rune,
            total_value_locked_usd=total_pooled_usd + total_bonded_usd,
        )

    async def get_swap_volume_stats(self):
        # Volume stats
        volume_recorder: VolumeRecorder = self.deps.volume_recorder
        seconds = self.tally_days_period * DAY
        curr_volume_stats, prev_volume_stats = await volume_recorder.get_previous_and_current_sum(seconds)
        return prev_volume_stats, curr_volume_stats

    async def get_swap_number_stats(self) -> TxCountStats:
        # Transaction count stats
        tx_counter: TxCountRecorder = self.deps.tx_count_recorder
        return await tx_counter.get_stats(self.tally_days_period)
