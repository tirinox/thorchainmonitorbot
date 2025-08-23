import asyncio

from api.midgard.urlgen import free_url_gen
from jobs.fetch.base import BaseFetcher
from jobs.user_counter import UserCounterMiddleware
from lib.constants import THOR_BLOCK_TIME, thor_to_float
from lib.date_utils import parse_timespan_to_seconds, now_ts
from lib.depcont import DepContainer
from models.net_stats import NetworkStats


class NetworkStatisticsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.net_summary.fetch_period)
        super().__init__(deps, sleep_period)
        self.step_sleep = deps.cfg.sleep_step
        self.swap_stats_days = 15

    async def _get_stats(self, ns: NetworkStats):
        j = await self.deps.midgard_connector.request(free_url_gen.url_stats())

        usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()

        ns.usd_per_rune = usd_per_rune

        ns.add_count = int(j['addLiquidityCount'])
        ns.added_rune = thor_to_float(j['addLiquidityVolume'])

        ns.withdraw_count = int(j['withdrawCount'])
        ns.withdrawn_rune = thor_to_float(j['withdrawVolume'])

        ns.loss_protection_paid_rune = thor_to_float(j.get('impermanentLossProtectionPaid', 0))

        ns.swaps_total = int(j['swapCount'])
        ns.swaps_24h = int(j['swapCount24h'])
        ns.swaps_30d = int(j['swapCount30d'])
        ns.unique_swapper_count = int(j.get('uniqueSwapperCount', 0))  # fixme: zero for Midgard 2.12.2
        ns.swap_volume_rune = thor_to_float(j['swapVolume'])

        ns.switched_rune = thor_to_float(j.get('switchedRune', 0))

    async def _get_network(self, ns: NetworkStats):
        j = await self.deps.midgard_connector.request(free_url_gen.url_network())

        ns.active_nodes = int(j['activeNodeCount'])
        ns.standby_nodes = int(j['standbyNodeCount'])

        ns.bonding_apy = float(j['bondingAPY']) * 100.0
        ns.liquidity_apy = float(j['liquidityAPY']) * 100.0

        ns.reserve_rune = thor_to_float(j['totalReserve'])

        next_cool_cd = int(j['poolActivationCountdown'])
        ns.next_pool_activation_ts = now_ts() + THOR_BLOCK_TIME * next_cool_cd

        bonding_metrics: dict = j['bondMetrics']
        ns.total_active_bond_rune = thor_to_float(bonding_metrics['totalActiveBond'])
        stand_by_bond = thor_to_float(bonding_metrics['totalStandbyBond'])
        ns.total_bond_rune = ns.total_active_bond_rune + stand_by_bond

        ns.total_rune_lp = thor_to_float(j['totalPooledRune'])

    KEY_CONST_MIN_RUNE_POOL_DEPTH = 'MinRunePoolDepth'

    async def _get_pools(self, ns: NetworkStats):
        ph = await self.deps.pool_cache.get()
        pools = ph.pool_info_map

        active_pools = [p for p in pools.values() if p.is_enabled]
        pending_pools = [p for p in pools.values() if not p.is_enabled]
        ns.active_pool_count = len(active_pools)
        ns.pending_pool_count = len(pending_pools)

        min_pool_depth_rune = self.deps.mimir_const_holder.get_constant(self.KEY_CONST_MIN_RUNE_POOL_DEPTH)

        if pending_pools:
            pending_pools = [p for p in pending_pools if
                             not p.is_virtual and p.balance_rune >= min_pool_depth_rune]
            pending_pools = list(sorted(pending_pools, key=lambda p: p.balance_rune, reverse=True))
            ns.next_pool_to_activate = pending_pools[0].asset if pending_pools else None

    async def _get_swap_stats(self, ns: NetworkStats):
        swap_stats = await self.deps.midgard_connector.query_swap_stats(count=self.swap_stats_days, interval='day')
        if swap_stats:
            ns.swap_stats = swap_stats.last_whole_interval
            ns.synth_volume_24h = (
                thor_to_float(ns.swap_stats.synth_mint_volume + ns.swap_stats.synth_redeem_volume)
            )
            ns.synth_op_count = ns.swap_stats.synth_mint_count + ns.swap_stats.synth_redeem_count

            ns.trade_volume_24h = (
                thor_to_float(ns.swap_stats.to_trade_volume + ns.swap_stats.from_trade_volume)
            )
            ns.trade_op_count = ns.swap_stats.to_trade_count + ns.swap_stats.from_trade_count

            ns.swap_volume_24h = thor_to_float(ns.swap_stats.total_volume)
        else:
            self.logger.error('Failed to get swap history from Midgard!')

    async def _get_user_stats(self, ns: NetworkStats):
        counter = UserCounterMiddleware(self.deps)
        stats = await counter.get_main_stats()
        ns.users_daily = stats.dau_yesterday
        ns.users_monthly = stats.mau

    async def _get_rune_pool_stats(self, ns: NetworkStats):
        runepool = await self.deps.thor_connector.query_runepool()
        if runepool:
            ns.total_rune_pool = thor_to_float(runepool.providers.current_deposit)
            ns.total_rune_pol = thor_to_float(runepool.reserve.current_deposit)
        else:
            self.logger.error('Failed to get RUNE pool stats from')

    async def fetch(self) -> NetworkStats:
        ns = NetworkStats()
        usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()
        ns.usd_per_rune = usd_per_rune

        await self._get_stats(ns),
        await asyncio.sleep(self.step_sleep)

        await self._get_network(ns)
        await asyncio.sleep(self.step_sleep)

        await self._get_pools(ns)
        await asyncio.sleep(self.step_sleep)

        await self._get_swap_stats(ns)
        await asyncio.sleep(self.step_sleep)

        await self._get_user_stats(ns)
        await asyncio.sleep(self.step_sleep)

        await self._get_rune_pool_stats(ns)

        ns.date_ts = int(now_ts())
        return ns
