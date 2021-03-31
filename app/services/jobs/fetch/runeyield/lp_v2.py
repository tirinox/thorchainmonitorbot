import asyncio
import datetime

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.jobs.midgard import MidgardURLGenBase
from services.lib.constants import NetworkIdents
from services.lib.depcont import DepContainer
from services.models.stake_info import CurrentLiquidity, StakePoolReport


# MULTI-chain

# https://mctn.vercel.app/dashboard?thor=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e  multi-chain
# FEES:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/fee?address=tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr|tb1qsasla0n6rjgwr6s4pa8jrqmvzzr0vfugulyyf0&pool=BTC.BTC

# thor address vs on-chain address (search for matches)
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/pooladdress?address=tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr

# Liquidity report itself!
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/poollist?address=tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr&isDev

# Midgard pool info https://testnet.midgard.thorchain.info/v2/pool/BTC.BTC
# Weekly: not yet
# https://testnet.midgard.thorchain.info/v2/member/tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e


class AsgardConsumerConnectorV2(AsgardConsumerConnectorBase):
    """
        Multichain Testnet/Chaosnet and Midgard V2 and app.runeyield.info connector
    """

    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        super().__init__(deps, ppf, url_gen)
        network = deps.cfg.network_id
        if network == NetworkIdents.TESTNET_MULTICHAIN:
            self.base_url = 'https://multichain-asgard-consumer-api.vercel.app'
        else:
            self.base_url = 'https://multichain-asgard-consumer-api.vercel.app'  # todo: set production URL

    def url_asgard_consumer_liquidity(self, address):
        return f"{self.base_url}/api/v2/member/poollist?address={address}&isDev"

    async def get_my_pools(self, address):
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            try:
                my_pools = j.get('pools', [])
                return [p['pool'] for p in my_pools if 'pool' in p]
            except KeyError:
                return []

    async def _fetch_one_pool_liquidity_info(self, address, pool):
        url = self.url_asgard_consumer_liquidity(address)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            raw_response = await resp.json()
            return next(CurrentLiquidity.from_asgard(item) for item in raw_response if item['pool'] == pool)

    async def _fetch_all_pool_liquidity_info(self, address, my_pools=None) -> dict:
        url = self.url_asgard_consumer_liquidity(address)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            raw_response = await resp.json()
            liqs = [CurrentLiquidity.from_asgard(item) for item in raw_response]
            return {c.pool: c for c in liqs}

    async def _fetch_all_pools_weekly_charts(self, address, pools):
        raise NotImplementedError


"""
OLD:

{
pool: "BNB.XRP-BF2",
runestake: "21145832937",
assetstake: "36174400000",
poolunits: "9419492540",
assetwithdrawn: "0",
runewithdrawn: "0",
totalstakedasset: "72348772633.5275",
totalstakedrune: "42291681871.14974",
totalstakedusd: "37873607962.29814",
totalunstakedasset: "0",
totalunstakedrune: "0",
totalunstakedusd: "0",
firststake: 1607883029,
laststake: 1607883029
}

NEW: 

[
{
pool: "BTC.BTC",
runestake: "2848839101",
assetstake: "88680",
poolunits: "1575870593",
runewithdrawn: "0",
assetwithdrawn: "0",
totalstakedrune: "5375271772.8529215",
totalstakedasset: "2848839104.112746",
totalstakedusd: "25904730573.309494",
totalstakedbtc: "188676.74809912662",
totalunstakedrune: "0",
totalunstakedasset: "0",
totalunstakedusd: "0",
totalunstakedbtc: "0",
firststake: 1617165163,
laststake: 1617165163
},
{
pool: "LTC.LTC",
runestake: "416327816",
assetstake: "4999000",
poolunits: "252559809",
runewithdrawn: "0",
assetwithdrawn: "0",
totalstakedrune: "832652736.8814805",
totalstakedasset: "416387841.23449016",
totalstakedusd: "4012754279.509747",
totalstakedbtc: "29224.77038528807",
totalunstakedrune: "0",
totalunstakedasset: "0",
totalunstakedusd: "0",
totalunstakedbtc: "0",
firststake: 1617165504,
laststake: 1617165504
}
]

"""
