import asyncio
import json
from itertools import chain
from operator import attrgetter
from typing import NamedTuple, Optional, List

from services.lib.constants import thor_to_float
from services.lib.cooldown import Cooldown
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import short_dollar
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfoMap
from services.models.price import RuneMarketInfo
from services.models.time_series import TimeSeries


class SaverVault(NamedTuple):
    asset: str
    number_of_savers: int
    total_asset_saved: float
    total_asset_as_usd: float
    total_asset_as_rune: float
    apr: float
    asset_cap: float
    runes_earned: float

    @property
    def percent_of_cap_filled(self):
        return self.total_asset_saved / self.asset_cap * 100.0 if self.asset_cap else 0.0

    @property
    def usd_per_rune(self):
        return self.total_asset_as_usd / self.total_asset_as_rune

    @property
    def usd_per_asset(self):
        return self.total_asset_as_usd / self.total_asset_saved


class AllSavers(NamedTuple):
    total_unique_savers: int
    pools: List[SaverVault]

    @property
    def total_usd_saved(self) -> float:
        return sum(s.total_asset_as_usd for s in self.pools)

    @property
    def total_rune_saved(self) -> float:
        return sum(s.total_asset_as_rune for s in self.pools)

    @property
    def apr_list(self):
        return [s.apr for s in self.pools]

    @property
    def average_apr(self) -> float:
        if not self.pools:
            return 0.0
        return sum(self.apr_list) / len(self.pools)

    @property
    def min_apr(self):
        return min(self.apr_list)

    @property
    def max_apr(self):
        return max(self.apr_list)

    @property
    def as_dict(self):
        d = self._asdict()
        d['pools'] = [v._asdict() for v in self.pools]
        return d

    @classmethod
    def load_from_ts_points(cls, point) -> Optional['AllSavers']:
        try:
            j = json.loads(point['json'])
        except (json.JSONDecodeError, KeyError, TypeError):
            return

        try:
            savers = cls(**j)
            # noinspection PyArgumentList
            return savers._replace(pools=[SaverVault(**v) for v in savers.pools])
        except TypeError:
            return

    def sort_pools(self, key='apr', reverse=False):
        self.pools.sort(key=attrgetter(key), reverse=reverse)
        return self

    def get_top_vaults(self, criterion: str, n=None, descending=True) -> List[SaverVault]:
        vault_list = list(self.pools)
        vault_list.sort(key=attrgetter(criterion), reverse=descending)
        return vault_list if n is None else vault_list[:n]

    @property
    def total_rune_earned(self):
        return sum(p.runes_earned for p in self.pools)

    @property
    def overall_fill_cap_percent(self):
        overall_saved = sum(p.total_asset_saved * p.usd_per_asset for p in self.pools)
        overall_cap = sum(p.asset_cap * p.usd_per_asset for p in self.pools)
        return overall_saved / overall_cap * 100.0


class EventSaverStats(NamedTuple):
    previous_stats: Optional[AllSavers]
    current_stats: AllSavers
    usd_per_rune: float


class SaversStatsNotifier(WithDelegates, INotified, WithLogger):
    MAX_POINTS = 10_000

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.ts = TimeSeries('SaverStats', deps.db)

        cd_write = deps.cfg.as_interval('saver_stats.save_stats_period', '1h')
        self.cd_write_stats = Cooldown(deps.db, 'SaverStats:Write', cd_write)
        cd_notify = deps.cfg.as_interval('saver_stats.period', '7d')
        self.cd_notify = Cooldown(deps.db, 'SaverStats:Notify', cd_notify)

    async def get_one_pool_members(self, asset, height=0):
        return await self.deps.thor_connector.query_savers(asset, height=height)

    async def get_all_savers(self, pool_map: PoolInfoMap, usd_per_rune, block_no):
        active_pools = [p for p in pool_map.values() if p.is_enabled and p.savers_units > 0]
        per_pool_members = await asyncio.gather(
            *(self.get_one_pool_members(p.asset) for p in active_pools)
        )

        max_synth_per_asset_ratio = self.deps.mimir_const_holder.get_max_synth_per_asset_depth()

        savers = AllSavers(
            # none?
            total_unique_savers=len(set(chain(*per_pool_members))),
            pools=[SaverVault(
                pool.asset,
                len(members),
                pool.savers_depth_float,
                pool.savers_depth_float * pool.runes_per_asset * usd_per_rune,
                pool.savers_depth_float * pool.runes_per_asset,
                apr=pool.get_savers_apr(block_no) * 100.0,
                asset_cap=thor_to_float(pool.get_synth_cap_in_asset(max_synth_per_asset_ratio)),
                runes_earned=pool.saver_growth_rune
            ) for pool, members in zip(active_pools, per_pool_members)]
        )
        savers.sort_pools()
        return savers

    async def save_savers(self, savers: AllSavers):
        d = savers.as_dict
        await self.ts.add_as_json(d)
        await self.ts.trim_oldest(self.MAX_POINTS)

    async def get_previous_saver_stats(self, ago_sec: float) -> Optional[AllSavers]:
        tolerance = self.cd_write_stats.cooldown * 1.5
        point, _ = await self.ts.get_best_point_ago(ago_sec, tolerance)
        return AllSavers.load_from_ts_points(point)

    async def do_notification(self, current_savers: AllSavers):
        previous_savers = await self.get_previous_saver_stats(self.cd_notify.cooldown)
        await self.pass_data_to_listeners(EventSaverStats(
            previous_savers, current_savers,
            usd_per_rune=self.deps.price_holder.usd_per_rune
        ))

    async def on_data(self, sender, rune_market: RuneMarketInfo):
        if await self.cd_write_stats.can_do():
            self.logger.info('Start loading saver stats...')
            savers = await self.get_all_savers(rune_market.pools,
                                               self.deps.price_holder.usd_per_rune,
                                               self.deps.last_block_store.last_thor_block)

            self.logger.info(f'Finished loading saver stats: '
                             f'{savers.total_unique_savers} total savers, '
                             f'avg APR = {savers.average_apr:.02f}% '
                             f'total saved = {short_dollar(savers.total_usd_saved)}')
            await self.save_savers(savers)
            await self.cd_write_stats.do()

            if await self.cd_notify.can_do():
                await self.do_notification(savers)
                await self.cd_notify.do()
