import asyncio
import logging

from services.lib.depcont import DepContainer
from services.models.stake_info import CurrentLiquidity

MIDGARD_MY_POOLS = 'https://chaosnet-midgard.bepswap.com/v1/stakers/{address}'
MIDGARD_POOL_LIQUIDITY = 'https://chaosnet-midgard.bepswap.com/v1/pools/detail?asset={pools}&view=simple'

ASGRAD_CONSUMER_WEEKLY_HISTORY = 'https://asgard-consumer.vercel.app/api/weekly?address={address}&pool={pool}'
ASGRAD_CONSUMER_CURRENT_LIQUIDITY = 'https://asgard-consumer.vercel.app/api/v2/history/liquidity?address={address}&pools={pool}'

COIN_LOGO = 'https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/binance/assets/{asset}/logo.png'



class LiqPoolFetcher:
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger('LiqPoolFetcher')

    async def get_my_pools(self, address):
        url = MIDGARD_MY_POOLS.format(address=address)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            my_pools = j['poolsArray']
            return my_pools

    async def get_current_liquidity(self, address, pool):
        url = ASGRAD_CONSUMER_CURRENT_LIQUIDITY.format(address=address, pool=pool)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return CurrentLiquidity.from_asgard(j)

    async def fetch(self, address, chain):
        my_pools = await self.get_my_pools(address)
        cur_liquidity = await asyncio.gather(*(self.get_current_liquidity(address, pool) for pool in my_pools))
        return {c.pool: c for c in cur_liquidity}
