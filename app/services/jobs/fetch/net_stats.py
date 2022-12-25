import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.jobs.ilp_summer import ILPSummer
from services.jobs.user_counter import UserCounter
from services.lib.constants import THOR_BLOCK_TIME, thor_to_float
from services.lib.date_utils import parse_timespan_to_seconds, now_ts, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import free_url_gen
from services.models.net_stats import NetworkStats
from services.models.swap_history import SwapHistoryResponse


class NetworkStatisticsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.net_summary.fetch_period)
        super().__init__(deps, sleep_period)

    async def _get_stats(self, ns: NetworkStats):
        j = await self.deps.midgard_connector.request(free_url_gen.url_stats())

        ns.usd_per_rune = float(j.get('runePriceUSD', self.deps.price_holder.usd_per_rune))

        ns.add_count = int(j['addLiquidityCount'])
        ns.added_rune = thor_to_float(j['addLiquidityVolume'])

        ns.withdraw_count = int(j['withdrawCount'])
        ns.withdrawn_rune = thor_to_float(j['withdrawVolume'])

        ns.loss_protection_paid_rune = thor_to_float(j['impermanentLossProtectionPaid'])

        ns.swaps_total = int(j['swapCount'])
        ns.swaps_24h = int(j['swapCount24h'])
        ns.swaps_30d = int(j['swapCount30d'])
        ns.unique_swapper_count = int(j.get('uniqueSwapperCount', 0))  # fixme: zero for Midgard 2.12.2
        ns.swap_volume_rune = thor_to_float(j['swapVolume'])

        ns.switched_rune = thor_to_float(j['switchedRune'])
        ns.total_rune_pooled = thor_to_float(j['runeDepth'])

    async def _get_network(self, ns: NetworkStats):
        j = await self.deps.midgard_connector.request(free_url_gen.url_network())

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
        pools = await self.deps.pool_fetcher.load_pools()

        active_pools = [p for p in pools.values() if p.is_enabled]
        pending_pools = [p for p in pools.values() if not p.is_enabled]
        ns.active_pool_count = len(active_pools)
        ns.pending_pool_count = len(pending_pools)

        min_pool_depth_rune = self.deps.mimir_const_holder.get_constant(self.KEY_CONST_MIN_RUNE_POOL_DEPTH)

        pending_pools = list(sorted(pending_pools, key=lambda p: p.balance_rune, reverse=True))
        if pending_pools:
            best_pool = pending_pools[0]
            if best_pool.balance_rune >= min_pool_depth_rune:
                ns.next_pool_to_activate = pending_pools[0].asset
            else:
                ns.next_pool_to_activate = None

    async def _get_swap_stats(self, ns: NetworkStats):
        j = await self.deps.midgard_connector.request(free_url_gen.url_for_swap_history(days=1))
        swap_meta = SwapHistoryResponse.from_json(j).meta
        ns.synth_volume_24h = thor_to_float(swap_meta.synth_mint_volume) + thor_to_float(swap_meta.synth_redeem_volume)
        ns.synth_op_count = swap_meta.synth_mint_count + swap_meta.synth_redeem_count
        ns.swap_volume_24h = thor_to_float(swap_meta.total_volume)

    async def _get_ilp_24h_payouts(self, ns: NetworkStats):
        ns.loss_protection_paid_24h_rune = await ILPSummer(self.deps).ilp_sum(period=DAY)

    async def _get_user_stats(self, ns: NetworkStats):
        counter = UserCounter(self.deps)
        stats = await counter.get_main_stats()
        ns.users_daily = stats.dau_yesterday
        ns.users_monthly = stats.mau

    async def fetch(self) -> NetworkStats:
        ns = NetworkStats()
        ns.usd_per_rune = self.deps.price_holder.usd_per_rune
        await asyncio.gather(
            self._get_stats(ns),
            self._get_network(ns),
            self._get_pools(ns),
            self._get_swap_stats(ns),
            self._get_ilp_24h_payouts(ns),
            self._get_user_stats(ns),
        )
        ns.date_ts = now_ts()
        return ns
