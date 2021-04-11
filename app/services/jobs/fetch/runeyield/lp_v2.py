import asyncio
import datetime
from typing import Union, List, NamedTuple

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase, YieldSummary
from services.lib.midgard.urlgen import MidgardURLGenBase
from services.lib.constants import NetworkIdents
from services.lib.depcont import DepContainer
from services.models.lp_info import CurrentLiquidity, FeeRequest, LiquidityPoolReport, FeeReport


class CompoundAddress(NamedTuple):
    addresses: str
    pool: str


class AsgardConsumerConnectorV2(AsgardConsumerConnectorBase):
    """
        Multichain Testnet/Chaosnet and Midgard V2 and app.runeyield.info connector
    """

    # override
    async def get_my_pools(self, address):
        compound_addresses = await self.get_compound_addresses(address)
        return [p.pool for p in compound_addresses]

    # override
    async def generate_yield_report_single_pool(self, address: str, pool: str):
        comp_addresses = await self.get_compound_addresses(address)
        comp_address_for_pool = next(ca for ca in comp_addresses if ca.pool == pool)

        liq_map = await self._fetch_all_pool_liquidity_info(address)
        liq = liq_map[pool]
        stake_report = await self._generate_yield_report(comp_address_for_pool, liq)
        return stake_report

    # override
    async def generate_yield_summary(self, address, pools: List[str]):
        comp_addresses = await self.get_compound_addresses(address)
        liqs_dict = await self._fetch_all_pool_liquidity_info(address)

        reports = [
            self._generate_yield_report(comp_addr, liqs_dict[comp_addr.pool])
            for comp_addr in comp_addresses
        ]

        pools = list(liqs_dict.keys())
        weekly_charts, *stake_reports = await asyncio.gather(self._fetch_all_pools_weekly_charts(address, pools),
                                                             *reports)
        return YieldSummary(stake_reports, weekly_charts)

    # -----------

    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        super().__init__(deps, ppf, url_gen)
        network = deps.cfg.network_id
        if network == NetworkIdents.TESTNET_MULTICHAIN:
            self.base_url = 'https://multichain-asgard-consumer-api.vercel.app'
        else:
            self.base_url = 'https://multichain-asgard-consumer-api.vercel.app'  # todo: set production URL

    def url_asgard_consumer_liquidity(self, address):
        return f"{self.base_url}/api/v2/member/poollist?address={address}&isDev"

    def url_asgard_consumer_fees(self, addresses: Union[list, str], pool):
        if isinstance(addresses, (list, tuple)):
            addresses = '|'.join(addresses)
        return f"{self.base_url}/v2/fee1?address={addresses}&pool={pool}"

    def url_asgard_consumer_compound_addresses(self, address):
        return f"{self.base_url}/api/v2/member/pooladdress?address={address}"

    async def get_compound_addresses(self, address: str):
        url = self.url_asgard_consumer_compound_addresses(address)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            response = await resp.json()
            try:
                return [CompoundAddress(
                    item.get('address', ''),
                    item.get('pool', '')
                ) for item in response]
            except KeyError:
                return []

    async def _get_fee_report(self, comp_addr) -> FeeReport:
        # todo: you must ask with thorADDRES|assetADDRESS otherwise -> fail; know your collateral address!
        url = self.url_asgard_consumer_fees(comp_addr.addresses, comp_addr.pool)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return FeeRequest.parse_from_asgard(j[0])

    async def _fetch_all_pool_liquidity_info(self, address) -> dict:
        url = self.url_asgard_consumer_liquidity(address)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            raw_response = await resp.json()
            liqs = [CurrentLiquidity.from_asgard(item) for item in raw_response]
            return {c.pool: c for c in liqs}

    async def _fetch_all_pools_weekly_charts(self, address, pools):
        return {}

    async def _generate_yield_report(self, comp_address: CompoundAddress, liq: CurrentLiquidity) -> LiquidityPoolReport:
        try:
            first_stake_dt = datetime.datetime.utcfromtimestamp(liq.first_stake_ts)
            # get prices at the moment of first stake
            usd_per_rune_start, usd_per_asset_start = await self.ppf.get_usd_price_of_rune_and_asset_by_day(
                liq.pool,
                first_stake_dt.date())
        except Exception as e:
            self.logger.exception(e, exc_info=True)
            usd_per_rune_start, usd_per_asset_start = None, None

        fees = await self._get_fee_report(comp_address)

        d = self.deps
        stake_report = LiquidityPoolReport(
            d.price_holder.usd_per_asset(liq.pool),
            d.price_holder.usd_per_rune,
            usd_per_asset_start, usd_per_rune_start,
            liq, fees=fees,
            pool=d.price_holder.pool_info_map.get(liq.pool)
        )
        return stake_report



# MULTI-chain

# https://mctn.vercel.app/dashboard?thor=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e  multi-chain
# https://mctn.vercel.app/dashboard?thor=tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh

# FEES:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/fee?address=tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh|0x8edafa9247d10d2f8c38be2a3448e302bc516054&pool=ETH.USDT-0X62E273709DA575835C7F6AEF4A31140CA5B1D190
# FEE_1

# POST : https://asgard-consumer.vercel.app/v2/fee1?address=bnb1h9zxfev58qxjf435crjwc0jp4yhr0x3289j6f3&pool=BNB.XRP-BF2
# post data: {liquidityTokenBalance: 94.1949254
# liquidityTokenTotalSupply: 16008.80719301
# pair: "BNB.XRP-BF2"
# reserve0: 16553.73782158
# reserve1: 236526.506849
# reserveUSD: 280194.0895413372
# token0PriceUSD: 8.463166825563317
# token1PriceUSD: 0.5923101247172582}

# thor address vs on-chain address (search for matches)  ==> important for Fees
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/pooladdress?address=tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr
# [,…]
# 0: {address: "tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr|tb1q5alruuduma22wp5jrhhut3ahnpmk3w7eqpcqpw",…}
#    address: "tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr|tb1q5alruuduma22wp5jrhhut3ahnpmk3w7eqpcqpw"
#    pool: "BTC.BTC"
# 1: {,…}
#    address: "tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr|tltc1q5alruuduma22wp5jrhhut3ahnpmk3w7eef6738"
#    pool: "LTC.LTC"

# Liquidity report itself!
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/poollist?address=tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr&isDev

# Midgard pool info https://testnet.midgard.thorchain.info/v2/pool/BTC.BTC
# OR (they are same!)
# https://multichain-asgard-consumer-api.vercel.app/v2/midgard/pool?pool=BTC.BTC
# Weekly: not yet
# https://testnet.midgard.thorchain.info/v2/member/tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e

"""
Dialog wants features:
1. get my pools
2. get liq report for 1 pool
3. get liq report summary!
"""
