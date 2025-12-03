import asyncio

from api.midgard.urlgen import free_url_gen
from jobs.fetch.cached.base import CachedDataSource
from jobs.fetch.circulating import RuneCirculatingSupplyFetcher
from jobs.fetch.gecko_price import get_thorchain_coin_gecko_info, gecko_market_volume, gecko_market_cap_rank, \
    gecko_ticker_price
from jobs.fetch.net_stats import NetworkStatisticsFetcher
from lib.constants import DEFAULT_CEX_NAME, DEFAULT_CEX_BASE_ASSET, thor_to_float, ThorRealms
from lib.date_utils import MINUTE
from lib.depcont import DepContainer
from lib.utils import retries
from models.circ_supply import RuneCirculatingSupply, RuneHoldEntry
from models.price import RuneMarketInfo


class RuneMarketInfoCache(CachedDataSource[RuneMarketInfo]):
    """
    Fetches swap history from the cache.
    """

    def __init__(self, deps: DepContainer, cache_period=5 * MINUTE):
        # pool = None means all pools, otherwise it filters by the specified pool
        super().__init__(cache_period, retry_times=5, retry_exponential_growth_factor=2)
        self.deps = deps
        self.cex_name = deps.cfg.as_str('price.cex_reference.cex', DEFAULT_CEX_NAME)
        self.cex_pair = deps.cfg.as_str('price.cex_reference.pair', DEFAULT_CEX_BASE_ASSET)
        self.step_delay = 1.0

        self.logger.info(f'Reference is RUNE/${self.cex_pair} at "{self.cex_name}" CEX.')

    async def _load(self) -> RuneMarketInfo:
        info = await self.get_rune_market_info_from_api()
        if not info.is_valid:
            raise ValueError(f"RuneMarketInfo is invalid: {info}")
        return info

    @retries(5)
    async def total_pooled_rune(self):
        j = await self.deps.midgard_connector.request(free_url_gen.url_network())
        total_pooled_rune = j.get('totalPooledRune', 0)
        return thor_to_float(total_pooled_rune)

    def get_supply_fetcher(self):
        return RuneCirculatingSupplyFetcher(
            self.deps.session,
            thor=self.deps.thor_connector,
            midgard=self.deps.midgard_connector,
            step_sleep=self.deps.cfg.sleep_step
        )

    @retries(5)
    async def get_full_supply_info(self) -> RuneCirculatingSupply:
        supply_info = await self.get_supply_fetcher().fetch()
        supply_info = await self._enrich_circulating_supply(supply_info)
        return supply_info

    async def _enrich_circulating_supply(self, supply: RuneCirculatingSupply) -> RuneCirculatingSupply:
        ns = await NetworkStatisticsFetcher(self.deps, 0).fetch()

        if ns:
            supply.set_holder(RuneHoldEntry('bond_module', int(ns.total_active_bond_rune), 'Bonded', ThorRealms.BONDED))
            supply.set_holder(RuneHoldEntry('pool_module', int(ns.total_rune_lp), 'Pooled', ThorRealms.LIQ_POOL))
            supply.set_holder(RuneHoldEntry('pol', int(ns.total_rune_pol), 'POL', ThorRealms.POL))
            supply.set_holder(RuneHoldEntry('runepool', int(ns.total_rune_pool), 'POL', ThorRealms.RUNEPOOL))
        else:
            self.logger.warning('No net stats! Failed to enrich circulating supply data with pool/bonding info!')

        # note: do we really need it?
        # nodes = self.deps.node_holder.nodes
        # if nodes:
        #     for node in nodes:
        #         if node.bond > 0:
        #             supply.set_holder(
        #                 RuneHoldEntry(node.node_address, int(node.bond), node.status, ThorRealms.BONDED_NODE)
        #             )
        # else:
        #     self.logger.warning('No nodes available! Failed to enrich circulating supply data with node info!')
        return supply

    async def get_rune_market_info_from_api(self) -> RuneMarketInfo:
        # Supply
        supply_info = await self.get_full_supply_info()
        await asyncio.sleep(self.step_delay)

        # CoinGecko stats
        gecko = await get_thorchain_coin_gecko_info(self.deps.session)
        if gecko:
            cex_price = gecko_ticker_price(gecko, self.cex_name, self.cex_pair)
            rank = gecko_market_cap_rank(gecko)
            trade_volume = gecko_market_volume(gecko)
        else:
            cex_price = 0
            rank = 0
            trade_volume = 0

        await asyncio.sleep(self.step_delay)

        # Total Rune in pools
        total_pooled_rune = await self.total_pooled_rune()

        supply_info: RuneCirculatingSupply
        circulating_rune = supply_info.circulating
        total_supply = supply_info.total

        if circulating_rune <= 0:
            raise ValueError(f"circulating is invalid ({circulating_rune})")

        price_holder = await self.deps.pool_cache.get()
        if not price_holder.pool_info_map or not price_holder.usd_per_rune:
            raise ValueError(f"pool_info_map is empty!")

        tvl_usd = total_pooled_rune * price_holder.usd_per_rune  # == tlv of non-rune assets

        fair_price = 3 * tvl_usd / circulating_rune  # The main formula of wealth!

        result = RuneMarketInfo(
            circulating=circulating_rune,
            pool_rune_price=price_holder.usd_per_rune,
            fair_price=fair_price,
            cex_price=cex_price,
            tvl_usd=tvl_usd,
            rank=rank,
            total_trade_volume_usd=trade_volume,
            total_supply=total_supply,
            supply_info=supply_info,
            stable_coins=self.deps.cfg.stable_coins,
        )
        self.logger.info(result)
        result.pools = price_holder.pool_info_map
        if not result.pools:
            result.pools = await self.deps.pool_fetcher.fetch()

        return result
