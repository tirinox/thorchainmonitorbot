import asyncio
import datetime

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.constants import THOR_DIVIDER_INV, THOR_BLOCK_TIME
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.net_stats import NetworkStats


class NetworkStatisticsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher):
        self.ppf = ppf
        sleep_period = parse_timespan_to_seconds(deps.cfg.net_summary.fetch_period)
        super().__init__(deps, sleep_period)
        self.url_gen = get_url_gen_by_network_id(deps.cfg.network_id)

    async def _get_stats(self, session, ns: NetworkStats):
        url_stats = self.url_gen.url_stats()
        self.logger.info(f"get Thor stats: {url_stats}")

        async with session.get(url_stats) as resp:
            j = await resp.json()

            ns.usd_per_rune = float(j['runePriceUSD'])

            ns.users_daily = int(j['dailyActiveUsers'])
            ns.users_monthly = int(j['monthlyActiveUsers'])

            ns.add_count = int(j['addLiquidityCount'])
            ns.added_rune = int(j['addLiquidityVolume']) * THOR_DIVIDER_INV

            ns.withdraw_count = int(j['withdrawCount'])
            ns.withdrawn_rune = int(j['withdrawVolume']) * THOR_DIVIDER_INV

            ns.loss_protection_paid_rune = int(j['impermanentLossProtectionPaid']) * THOR_DIVIDER_INV

            ns.swaps_total = int(j['swapCount'])
            ns.swaps_24h = int(j['swapCount24h'])
            ns.swaps_30d = int(j['swapCount30d'])
            ns.swap_volume_rune = int(j['swapVolume'])

            ns.switched_rune = int(j['switchedRune']) * THOR_DIVIDER_INV
            ns.total_rune_pooled = int(j['runeDepth']) * THOR_DIVIDER_INV

    async def _get_network(self, session, ns: NetworkStats):
        url_network = self.url_gen.url_network()
        self.logger.info(f"get Thor stats: {url_network}")

        async with session.get(url_network) as resp:
            j = await resp.json()

            ns.active_nodes = int(j['activeNodeCount'])
            ns.standby_nodes = int(j['standbyNodeCount'])

            ns.bonding_apy = float(j['bondingAPY'])
            ns.liquidity_apy = float(j['liquidityAPY'])

            ns.reserve_rune = int(j['totalReserve']) * THOR_DIVIDER_INV

            next_cool_cd = int(j['poolActivationCountdown'])
            ns.next_pool_activation_ts = datetime.datetime.now().timestamp() + THOR_BLOCK_TIME * next_cool_cd

            bonding_metrics = j['bondMetrics']
            ns.total_bond_rune = (
                                         int(bonding_metrics['totalActiveBond']) +
                                         int(bonding_metrics['totalStandbyBond'])
                                 ) * THOR_DIVIDER_INV

    async def _get_pools(self, _, ns: NetworkStats):
        pools = await self.ppf.get_current_pool_data_full()
        active_pools = [p for p in pools.values() if p.is_enabled]
        pending_pools = [p for p in pools.values() if not p.is_enabled]
        ns.active_pool_count = len(active_pools)
        ns.pending_pool_count = len(pending_pools)

        pending_pools = list(sorted(pending_pools, key=lambda p: p.balance_rune, reverse=True))
        if pending_pools:
            ns.next_pool_to_activate = pending_pools[0].asset

    async def fetch(self) -> NetworkStats:
        session = self.deps.session
        ns = NetworkStats()
        ns.usd_per_rune = self.deps.price_holder.usd_per_rune
        await asyncio.gather(
            self._get_stats(session, ns),
            self._get_network(session, ns),
            self._get_pools(session, ns)
        )
        return ns


#  https://midgard.thorchain.info/v2/stats
"""
{
	"addLiquidityCount": "1000",
	"addLiquidityVolume": "120909198406120",
	"dailyActiveUsers": "192",
	"impermanentLossProtectionPaid": "5325203346",
	"monthlyActiveUsers": "1208",
	"runeDepth": "48956111721455",
	"runePriceUSD": "14.206774942862193",
	"swapCount": "8016",
	"swapCount24h": "2076",
	"swapCount30d": "8016",
	"swapVolume": "192072956816435",
	"switchedRune": "329694619957060",
	"toAssetCount": "3320",
	"toRuneCount": "4696",
	"uniqueSwapperCount": "1208",
	"withdrawCount": "204",
	"withdrawVolume": "10146460744865"
}
"""
#  https://midgard.thorchain.info/v2/history/swaps?interval=day&count=100&to=1618670690
#  https://midgard.thorchain.info/v2/history/earnings?interval=day&count=100&to=1618670690
#  https://midgard.thorchain.info/v2/history/liquidity_changes?interval=day&count=100&to=1618670690
"""

"""
#  https://midgard.thorchain.info/v2/network
"""
{
	"activeBonds": [
		"23449124300",
		"30001892000000",
		"30012802647686",
		"30016344751512",
		"30020512048346",
		"30022155359872",
		"30022624167387"
	],
	"activeNodeCount": "7",
	"blockRewards": {
		"blockReward": "6163",
		"bondReward": "2634",
		"poolReward": "3529"
	},
	"bondMetrics": {
		"averageActiveBond": "25731397157014",
		"averageStandbyBond": "417000000",
		"maximumActiveBond": "30022624167387",
		"maximumStandbyBond": "494000002",
		"medianActiveBond": "30016344751512",
		"medianStandbyBond": "492000000",
		"minimumActiveBond": "23449124300",
		"minimumStandbyBond": "290000001",
		"totalActiveBond": "180119780099103",
		"totalStandbyBond": "1668000003"
	},
	"bondingAPY": "0.04994875195900006",
	"liquidityAPY": "0.12759794049140427",
	"nextChurnHeight": "233724",
	"poolActivationCountdown": "1605",
	"poolShareFactor": "0.5726441585889832",
	"standbyBonds": [
		"290000001",
		"392000000",
		"492000000",
		"494000002"
	],
	"standbyNodeCount": "4",
	"totalPooledRune": "48946381009728",
	"totalReserve": "194387319850"
}

"""
