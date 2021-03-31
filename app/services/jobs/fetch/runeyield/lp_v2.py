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
