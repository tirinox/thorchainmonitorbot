import asyncio

from services.lib.depcont import DepContainer
from services.models.stake_info import CurrentLiquidity

MIDGARD_MY_POOLS = 'https://chaosnet-midgard.bepswap.com/v1/stakers/{address}'
MIDGARD_POOL_LIQUIDITY = 'https://chaosnet-midgard.bepswap.com/v1/pools/detail?asset={pools}&view=simple'

ASGRAD_CONSUMER_WEEKLY_HISTORY = 'https://asgard-consumer.vercel.app/api/weekly?address={address}&pool={pool}'
ASGRAD_CONSUMER_CURRENT_LIQUIDITY = 'https://asgard-consumer.vercel.app/api/v2/history/liquidity?address={address}&pools={pool}'


def pool_share(rune_depth, asset_depth, stake_units, pool_unit):
    rune_share = (rune_depth * stake_units) / pool_unit
    asset_share = (asset_depth * stake_units) / pool_unit
    return rune_share, asset_share


class LiqPoolFetcher:
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_my_pools(self, address):
        url = MIDGARD_MY_POOLS.format(address=address)
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            my_pools = j['poolsArray']
            return my_pools

    async def get_current_liquidity(self, address, pool):
        url = ASGRAD_CONSUMER_CURRENT_LIQUIDITY.format(address=address, pool=pool)
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return CurrentLiquidity.from_asgard(j)

    async def fetch(self, address, chain):
        my_pools = await self.get_my_pools(address)
        cur_liquidity = await asyncio.gather(*(self.get_current_liquidity(address, pool) for pool in my_pools))
        print(cur_liquidity)



