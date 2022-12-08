import asyncio
from itertools import chain
from typing import NamedTuple, Optional

from services.lib.cooldown import Cooldown
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import short_dollar
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfoMap
from services.models.savers import SaverVault, AllSavers, get_savers_apr
from services.models.price import RuneMarketInfo, LastPriceHolder
from services.models.time_series import TimeSeries


class EventSaverStats(NamedTuple):
    previous_stats: Optional[AllSavers]
    current_stats: AllSavers
    price_holder: LastPriceHolder


class SaversStatsNotifier(WithDelegates, INotified, WithLogger):
    MAX_POINTS = 10_000

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.ts = TimeSeries('SaverStats_v2', deps.db)

        cd_write = deps.cfg.as_interval('saver_stats.save_stats_period', '1h')
        self.cd_write_stats = Cooldown(deps.db, 'SaverStats:Write', cd_write)
        cd_notify = deps.cfg.as_interval('saver_stats.period', '7d')
        self.cd_notify = Cooldown(deps.db, 'SaverStats:Notify', cd_notify)

    # todo: move to another place
    async def get_one_pool_members(self, asset, height=0):
        return await self.deps.thor_connector.query_savers(asset, height=height)

    async def get_all_savers(self, pool_map: PoolInfoMap, block_no):
        active_pools = [p for p in pool_map.values() if p.is_enabled and p.savers_units > 0]
        per_pool_members = await asyncio.gather(
            *(self.get_one_pool_members(p.asset, block_no) for p in active_pools)
        )

        max_synth_per_pool_depth = self.deps.mimir_const_holder.get_max_synth_per_pool_depth()

        pep_pool_savers = []

        for pool, members in zip(active_pools, per_pool_members):
            synth_cap = pool.get_synth_cap_in_asset_float(max_synth_per_pool_depth)

            pep_pool_savers.append(SaverVault(
                pool.asset,
                len(members),
                total_asset_saved=pool.savers_depth_float,
                total_asset_saved_usd=SaverVault.calc_total_saved_usd(pool.asset, pool.savers_depth_float, pool_map),
                apr=get_savers_apr(pool, block_no) * 100.0,
                asset_cap=synth_cap,
                runes_earned=pool.saver_growth_rune,
                synth_supply=pool.synth_supply_float,
            ))

        savers = AllSavers(
            # none?
            total_unique_savers=len(set(chain(*per_pool_members))),
            vaults=pep_pool_savers
        )

        savers.sort_vaults()
        return savers

    async def save_savers(self, savers: AllSavers):
        d = savers.as_dict
        await self.ts.add_as_json(d)
        await self.ts.trim_oldest(self.MAX_POINTS)

    async def get_previous_saver_stats(self, ago_sec: float) -> Optional[AllSavers]:
        tolerance = self.cd_write_stats.cooldown * 1.5
        point, _ = await self.ts.get_best_point_ago(ago_sec, tolerance)
        savers = AllSavers.load_from_ts_points(point)

        if savers:
            pool_map = self.deps.price_holder.pool_info_map
            savers.fill_total_usd(pool_map)

        return savers

    async def do_notification(self, current_savers: AllSavers):
        previous_savers = await self.get_previous_saver_stats(self.cd_notify.cooldown)
        await self.pass_data_to_listeners(EventSaverStats(
            previous_savers, current_savers,
            self.deps.price_holder,
        ))

    async def on_data(self, sender, rune_market: RuneMarketInfo):
        if await self.cd_write_stats.can_do():
            self.logger.info('Start loading saver stats...')

            savers = await self.get_all_savers(rune_market.pools,
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
