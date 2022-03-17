import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.constants import THOR_BLOCK_TIME, thor_to_float
from services.lib.date_utils import parse_timespan_to_seconds, now_ts
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import free_url_gen
from services.models.mimir import MimirHolder
from services.models.net_stats import NetworkStats


class NetworkStatisticsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.net_summary.fetch_period)
        super().__init__(deps, sleep_period)

    async def _get_stats(self, ns: NetworkStats):
        j = await self.deps.midgard_connector.request_random_midgard(free_url_gen.url_stats())

        ns.usd_per_rune = float(j.get('runePriceUSD', self.deps.price_holder.usd_per_rune))

        ns.users_daily = int(j['dailyActiveUsers'])
        ns.users_monthly = int(j['monthlyActiveUsers'])

        ns.add_count = int(j['addLiquidityCount'])
        ns.added_rune = thor_to_float(j['addLiquidityVolume'])

        ns.withdraw_count = int(j['withdrawCount'])
        ns.withdrawn_rune = thor_to_float(j['withdrawVolume'])

        ns.loss_protection_paid_rune = thor_to_float(j['impermanentLossProtectionPaid'])

        ns.swaps_total = int(j['swapCount'])
        ns.swaps_24h = int(j['swapCount24h'])
        ns.swaps_30d = int(j['swapCount30d'])
        ns.swap_volume_rune = thor_to_float(j['swapVolume'])

        ns.switched_rune = thor_to_float(j['switchedRune'])
        ns.total_rune_pooled = thor_to_float(j['runeDepth'])

    async def _get_network(self, ns: NetworkStats):
        j = await self.deps.midgard_connector.request_random_midgard(free_url_gen.url_network())

        ns.active_nodes = int(j['activeNodeCount'])
        ns.standby_nodes = int(j['standbyNodeCount'])

        ns.bonding_apy = float(j['bondingAPY']) * 100.0
        ns.liquidity_apy = float(j['liquidityAPY']) * 100.0

        ns.reserve_rune = thor_to_float(j['totalReserve'])

        next_cool_cd = int(j['poolActivationCountdown'])
        ns.next_pool_activation_ts = now_ts() + THOR_BLOCK_TIME * next_cool_cd

        bonding_metrics = j['bondMetrics']

        ns.total_active_bond_rune = thor_to_float(bonding_metrics['totalActiveBond'])

        stand_by_bond = thor_to_float(bonding_metrics['totalStandbyBond'])
        ns.total_bond_rune = ns.total_active_bond_rune + stand_by_bond

    KEY_CONST_MIN_RUNE_POOL_DEPTH = 'MinRunePoolDepth'

    async def _get_pools(self, ns: NetworkStats):
        ppf: PoolPriceFetcher = self.deps.price_pool_fetcher
        cmf: MimirHolder = self.deps.mimir_const_holder

        pools = await ppf.get_current_pool_data_full()

        active_pools = [p for p in pools.values() if p.is_enabled]
        pending_pools = [p for p in pools.values() if not p.is_enabled]
        ns.active_pool_count = len(active_pools)
        ns.pending_pool_count = len(pending_pools)

        min_pool_depth_rune = cmf.get_constant(self.KEY_CONST_MIN_RUNE_POOL_DEPTH)

        pending_pools = list(sorted(pending_pools, key=lambda p: p.balance_rune, reverse=True))
        if pending_pools:
            best_pool = pending_pools[0]
            if best_pool.balance_rune >= min_pool_depth_rune:
                ns.next_pool_to_activate = pending_pools[0].asset
            else:
                ns.next_pool_to_activate = None

    async def fetch(self) -> NetworkStats:
        ns = NetworkStats()
        ns.usd_per_rune = self.deps.price_holder.usd_per_rune
        await asyncio.gather(
            self._get_stats(ns),
            self._get_network(ns),
            self._get_pools(ns)
        )
        ns.date_ts = now_ts()
        return ns
