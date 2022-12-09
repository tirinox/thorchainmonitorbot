import asyncio
from itertools import chain
from typing import NamedTuple, Optional

from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import short_dollar
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfoMap
from services.models.price import RuneMarketInfo, LastPriceHolder
from services.models.savers import SaverVault, AllSavers, get_savers_apr
from services.notify.types.block_notify import LastBlockStore


class EventSaverStats(NamedTuple):
    previous_stats: Optional[AllSavers]
    current_stats: AllSavers
    price_holder: LastPriceHolder


class SaversStatsNotifier(WithDelegates, INotified, WithLogger):

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

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
            total_usd = SaverVault.calc_total_saved_usd(pool.asset, pool.savers_depth_float, pool_map)
            pep_pool_savers.append(SaverVault(
                pool.asset,
                len(members),
                total_asset_saved=pool.savers_depth_float,
                total_asset_saved_usd=total_usd,
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

    async def get_savers_event_dynamically(self, period,
                                           apr_period=7 * DAY,
                                           usd_per_rune=None, last_block_no=None) -> EventSaverStats:
        pf: PoolFetcher = self.deps.pool_fetcher
        block_store: LastBlockStore = self.deps.last_block_store
        shared_price_holder = self.deps.price_holder

        # Load the current state
        curr_pools = await pf.load_pools(height=last_block_no)

        usd_per_rune = usd_per_rune or shared_price_holder.calculate_rune_price_here(curr_pools)
        pf.fill_usd_in_pools(curr_pools, usd_per_rune)

        price_holder = LastPriceHolder(shared_price_holder.stable_coins)
        price_holder.usd_per_rune = usd_per_rune
        price_holder.pool_info_map = curr_pools

        last_block_no = last_block_no or block_store.last_thor_block

        curr_saver = await self.get_all_savers(curr_pools, last_block_no)

        # Load previous state to compare
        prev_saver, prev_pools = None, None
        if period:
            prev_block = block_store.block_time_ago(period, last_block=last_block_no)
            prev_pools = await pf.load_pools(height=prev_block, usd_per_rune=usd_per_rune)
            if prev_pools:
                prev_saver = await self.get_all_savers(prev_pools, prev_block)

        # Calculate current APR
        if apr_period == period:
            old_pools = prev_pools
        else:
            height_before = block_store.block_time_ago(apr_period, last_block=last_block_no)
            old_pools = await pf.load_pools(height=height_before)

        period_multiplier = 365 * DAY / apr_period
        for vault in curr_saver.vaults:
            pool = curr_pools.get(vault.asset)
            old_pool = old_pools.get(vault.asset)

            if not pool or not old_pool:
                continue

            saver_growth = pool.saver_growth
            saver_growth_before = old_pool.saver_growth
            saver_return = (saver_growth - saver_growth_before) / saver_growth_before * period_multiplier
            vault.apr = saver_return * 100.0

        return EventSaverStats(
            prev_saver, curr_saver, price_holder
        )

    async def on_data(self, sender, rune_market: RuneMarketInfo):
        if await self.cd_notify.can_do():

            period = max(DAY, self.cd_notify.cooldown)
            event = await self.get_savers_event_dynamically(period)
            if not event:
                self.logger.warning('Failed to load Savers data!')
                return

            savers = event.current_stats
            self.logger.info(f'Finished loading saver stats: '
                             f'{savers.total_unique_savers} total savers, '
                             f'avg APR = {savers.average_apr:.02f}% '
                             f'total saved = {short_dollar(savers.total_usd_saved)}')

            await self.pass_data_to_listeners(event)
            await self.cd_notify.do()
