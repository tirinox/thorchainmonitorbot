import asyncio
import datetime

from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.jobs.midgard import get_midgard_url
from services.models.stake_info import CurrentLiquidity, StakePoolReport, StakeDayGraphPoint


class AsgardConsumerConnectorV1(AsgardConsumerConnectorBase):
    """
    Chaosnet and Midgard V1 and RuneStake.info connector
    """

    def _url_midgard_my_pools(self, address):
        return get_midgard_url(self.deps.cfg, f"/stakers/{address}")

    @staticmethod
    def _url_asgard_consumer_weekly_history(address, pool):
        return f'https://asgard-consumer.vercel.app/api/weekly?address={address}&pool={pool}'

    @staticmethod
    def url_asgard_consumer_liquidity(address, pool):
        return f'https://asgard-consumer.vercel.app/api/v2/history/liquidity?address={address}&pools={pool}'

    async def get_my_pools(self, address):
        url = self._url_midgard_my_pools(address)
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

    async def _generate_yield_report(self, liq: CurrentLiquidity) -> StakePoolReport:
        try:
            first_stake_dt = datetime.datetime.utcfromtimestamp(liq.first_stake_ts)
            # get prices at the moment of first stake
            usd_per_rune_start, usd_per_asset_start = await self.ppf.get_usd_price_of_rune_and_asset_by_day(
                liq.pool,
                first_stake_dt.date())
        except Exception as e:
            self.logger.exception(e, exc_info=True)
            usd_per_rune_start, usd_per_asset_start = None, None

        d = self.deps
        stake_report = StakePoolReport(d.price_holder.usd_per_asset(liq.pool),
                                       d.price_holder.usd_per_rune,
                                       usd_per_asset_start, usd_per_rune_start,
                                       liq,
                                       d.price_holder.pool_info_map.get(liq.pool))
        return stake_report
