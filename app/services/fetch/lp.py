import asyncio
import logging

from services.fetch.pool_price import PoolPriceFetcher
from services.lib.depcont import DepContainer
from services.models.stake_info import CurrentLiquidity, StakePoolReport

MIDGARD_MY_POOLS = 'https://chaosnet-midgard.bepswap.com/v1/stakers/{address}'
MIDGARD_POOL_LIQUIDITY = 'https://chaosnet-midgard.bepswap.com/v1/pools/detail?asset={pools}&view=simple'

ASGRAD_CONSUMER_WEEKLY_HISTORY = 'https://asgard-consumer.vercel.app/api/weekly?address={address}&pool={pool}'
ASGRAD_CONSUMER_CURRENT_LIQUIDITY = \
    'https://asgard-consumer.vercel.app/api/v2/history/liquidity?address={address}&pools={pool}'


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

    async def fetch_liquidity_info(self, address):
        my_pools = await self.get_my_pools(address)
        cur_liquidity = await asyncio.gather(*(self.get_current_liquidity(address, pool) for pool in my_pools))
        return {c.pool: c for c in cur_liquidity}

    async def fetch_stake_report_for_pool(self, liq: CurrentLiquidity, ppf: PoolPriceFetcher) -> StakePoolReport:
        try:
            usd_per_rune_start, usd_per_asset_start = await ppf.get_usd_per_rune_asset_per_rune_by_day(
                liq.pool,
                liq.first_stake_ts)
        except:
            usd_per_rune_start, usd_per_asset_start = None, None

        d = self.deps
        stake_report = StakePoolReport(d.price_holder.usd_per_asset(liq.pool),
                                       d.price_holder.usd_per_rune,
                                       usd_per_asset_start, usd_per_rune_start,
                                       liq,
                                       d.price_holder.pool_info_map.get(liq.pool))
        return stake_report
