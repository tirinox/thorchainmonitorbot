import asyncio
import datetime

from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.jobs.midgard import get_midgard_url
from services.models.stake_info import CurrentLiquidity, StakePoolReport, StakeDayGraphPoint


class AsgardConsumerConnectorV1(AsgardConsumerConnectorBase):
    """
    Chaosnet and Midgard V1 and RuneStake.info connector
    """

    @staticmethod
    def _url_asgard_consumer_weekly_history(address, pool):
        return f'https://asgard-consumer.vercel.app/api/weekly?address={address}&pool={pool}'

    @staticmethod
    def url_asgard_consumer_liquidity(address, pool):
        return f'https://asgard-consumer.vercel.app/api/v2/history/liquidity?address={address}&pools={pool}'

    async def get_my_pools(self, address):
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            try:
                my_pools = j['poolsArray']
                return my_pools
            except KeyError:
                return None

    async def _fetch_one_pool_liquidity_info(self, address, pool):
        url = self.url_asgard_consumer_liquidity(address, pool)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return CurrentLiquidity.from_asgard(j)

    async def _fetch_one_pool_weekly_chart(self, address, pool):
        url = self._url_asgard_consumer_weekly_history(address, pool)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            try:
                return pool, [StakeDayGraphPoint.from_asgard(point) for point in j['data']]
            except TypeError:
                self.logger.warning(f'no weekly chart for {pool} @ {address}')
                return pool, None

    async def _fetch_all_pools_weekly_charts(self, address, pools):
        weekly_charts = await asyncio.gather(*[self._fetch_one_pool_weekly_chart(address, pool) for pool in pools])
        return dict(weekly_charts)

    async def _fetch_all_pool_liquidity_info(self, address, my_pools=None) -> dict:
        my_pools = (await self.get_my_pools(address)) if my_pools is None else my_pools
        cur_liquidity = await asyncio.gather(*(self._fetch_one_pool_liquidity_info(address, pool) for pool in my_pools))
        return {c.pool: c for c in cur_liquidity}
