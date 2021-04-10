import asyncio
import datetime
from typing import List

from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.models.stake_info import CurrentLiquidity, StakeDayGraphPoint, StakePoolReport, FeeReport


class AsgardConsumerConnectorV1(AsgardConsumerConnectorBase):
    """
    Chaosnet and Midgard V1 and RuneStake.info connector
    """

    # override
    async def generate_yield_summary(self, address, pools: List[str]):
        liqs = await self._fetch_all_pool_liquidity_info(address, pools)
        pools = list(liqs.keys())
        liqs = list(liqs.values())
        weekly_charts, stake_reports = await asyncio.gather(self._fetch_all_pools_weekly_charts(address, pools),
                                                            self._generate_yield_reports(address, liqs))
        return stake_reports, weekly_charts

    # override
    async def generate_yield_report_single_pool(self, address, pool):
        liq = await self._fetch_one_pool_liquidity_info(address, pool)
        stake_report = await self._generate_yield_report(address, liq)
        return stake_report

    # override
    async def get_my_pools(self, address) -> List[str]:
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            try:
                my_pools = j['poolsArray']
                return my_pools
            except KeyError:
                return []

    # ------------ implementation ----------

    @staticmethod
    def _url_asgard_consumer_weekly_history(address, pool):
        return f'https://asgard-consumer.vercel.app/api/weekly?address={address}&pool={pool}'

    @staticmethod
    def url_asgard_consumer_liquidity(address, pool):
        return f'https://asgard-consumer.vercel.app/api/v2/history/liquidity?address={address}&pools={pool}'

    @staticmethod
    def _url_asgard_consumer_fees(address, pool):
        return f'https://asgard-consumer.vercel.app/v2/fee1?address={address}&pool={pool}'

    async def _get_fee_report(self, address, pool, my_lp_points) -> FeeReport:
        url = self._url_asgard_consumer_fees(address, pool)
        self.logger.info(f'post: {url}')
        pool = self.deps.price_holder.find_pool(pool)
        report = pool.create_lp_position(my_lp_points, self.deps.price_holder.usd_per_rune)
        async with self.deps.session.post(url, data=report) as resp:
            j = await resp.json()
            return FeeReport.parse_from_asgard(j)

    async def _fetch_one_pool_liquidity_info(self, address, pool):
        url = self.url_asgard_consumer_liquidity(address, pool)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return CurrentLiquidity.from_asgard(j)

    async def _fetch_one_pool_weekly_chart(self, address, pool):
        url = self._url_asgard_consumer_weekly_history(address, pool)
        self.logger.info(f'get: {url}')
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

    async def _fetch_all_pool_liquidity_info(self, address, pools=None) -> dict:
        pools = (await self.get_my_pools(address)) if pools is None else pools
        cur_liquidity = await asyncio.gather(*(self._fetch_one_pool_liquidity_info(address, pool) for pool in pools))
        return {c.pool: c for c in cur_liquidity}

    async def _generate_yield_report(self, address, liq: CurrentLiquidity) -> StakePoolReport:
        try:
            first_stake_dt = datetime.datetime.utcfromtimestamp(liq.first_stake_ts)
            # get prices at the moment of first stake
            usd_per_rune_start, usd_per_asset_start = await self.ppf.get_usd_price_of_rune_and_asset_by_day(
                liq.pool,
                first_stake_dt.date())
        except Exception as e:
            self.logger.exception(e, exc_info=True)
            usd_per_rune_start, usd_per_asset_start = None, None

        fees = await self._get_fee_report(address, liq.pool, liq.pool_units)

        d = self.deps
        stake_report = StakePoolReport(
            d.price_holder.usd_per_asset(liq.pool),
            d.price_holder.usd_per_rune,
            usd_per_asset_start, usd_per_rune_start,
            liq, fees=fees,
            pool=d.price_holder.pool_info_map.get(liq.pool)
        )
        return stake_report

    async def _generate_yield_reports(self, address, liqs: List[CurrentLiquidity]) -> List[StakePoolReport]:
        result = await asyncio.gather(*[self._generate_yield_report(address, liq) for liq in liqs])
        return list(result)
