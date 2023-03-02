import asyncio
from datetime import datetime, timedelta
from itertools import chain

from services.jobs.fetch.pool_price import PoolFetcher, PoolInfoFetcherMidgard
from services.lib.async_cache import AsyncTTL
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfoMap
from services.models.price import LastPriceHolder
from services.models.savers import SaverVault, SaversBank, get_savers_apr, EventSaverStats
from services.notify.types.block_notify import LastBlockStore


class SaversStatsFetcher(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._pool_source = PoolInfoFetcherMidgard(self.deps, 0)

    async def get_one_pool_members(self, asset, height=0):
        return await self.deps.thor_connector.query_savers(asset, height=height)

    async def get_all_savers(self, pool_map: PoolInfoMap, block_no=0) -> SaversBank:
        block_no = block_no or self.deps.last_block_store.last_thor_block

        # Get savers members @ block #block_no
        active_pools = [p for p in pool_map.values() if p.is_enabled and p.savers_units > 0]
        per_pool_members = await asyncio.gather(
            *(self.get_one_pool_members(p.asset, block_no) for p in active_pools)
        )

        max_synth_per_pool_depth = self.deps.mimir_const_holder.get_max_synth_per_pool_depth()

        pep_pool_savers = []

        for pool, members in zip(active_pools, per_pool_members):
            synth_cap = pool.get_synth_cap_in_asset_float(max_synth_per_pool_depth)
            total_usd = SaverVault.calc_total_saved_usd(pool.asset, pool.savers_depth_float, pool_map)
            # rune_earned = (now.cumulative_yield - that_day.cumulative_yield) / asset_per_rune
            runes_earned = pool.saver_growth_rune  # fixme: invalid
            pep_pool_savers.append(SaverVault(
                pool.asset,
                len(members),
                total_asset_saved=pool.savers_depth_float,
                total_asset_saved_usd=total_usd,
                apr=get_savers_apr(pool, block_no) * 100.0,
                asset_cap=synth_cap,
                runes_earned=runes_earned,
                synth_supply=pool.synth_supply_float,
            ))

        savers = SaversBank(
            # none?
            total_unique_savers=len(set(chain(*per_pool_members))),
            vaults=pep_pool_savers
        )

        savers.sort_vaults()
        return savers

    async def get_savers_event_dynamically(self, period,
                                           usd_per_rune=None) -> EventSaverStats:
        pf: PoolFetcher = self.deps.pool_fetcher
        block_store: LastBlockStore = self.deps.last_block_store
        shared_price_holder = self.deps.price_holder

        # Load the current state
        curr_pools = await self._pool_source.fetch() or await pf.load_pools()

        usd_per_rune = usd_per_rune or shared_price_holder.calculate_rune_price_here(curr_pools)
        pf.fill_usd_in_pools(curr_pools, usd_per_rune)

        price_holder = LastPriceHolder(shared_price_holder.stable_coins)
        price_holder.usd_per_rune = usd_per_rune
        price_holder.pool_info_map = curr_pools

        last_block_no = block_store.last_thor_block

        curr_saver = await self.get_all_savers(curr_pools, last_block_no)

        # Load previous state to compare
        prev_saver, prev_pools = None, None
        if period:
            prev_block = block_store.block_time_ago(period, last_block=last_block_no)
            prev_pools = await pf.load_pools(height=prev_block, usd_per_rune=usd_per_rune)
            if prev_pools:
                prev_saver = await self.get_all_savers(prev_pools, prev_block)

        for vault in curr_saver.vaults:
            if pool := curr_pools.get(vault.asset):
                vault.apr = pool.savers_apr * 100.0 if pool else 0.0

        return EventSaverStats(
            prev_saver, curr_saver, price_holder
        )

    CACHE_TTL = 60

    @AsyncTTL(time_to_live=CACHE_TTL)
    async def get_savers_event_dynamically_cached(self, period,
                                                  usd_per_rune=None) -> EventSaverStats:
        return await self.get_savers_event_dynamically(period, usd_per_rune)

    async def on_data(self, sender, data):
        data = await self.get_all_savers(self.deps.price_holder.pool_info_map)
        await self.pass_data_to_listeners(data)
