import asyncio

from jobs.fetch.base import BaseFetcher
from jobs.fetch.circulating import RuneCirculatingSupplyFetcher
from lib.constants import TCY_DENOM, TCY_SYMBOL, THOR_BASIS_POINT_MAX, thor_to_float
from lib.depcont import DepContainer
from models.price import PriceHolder
from models.tcy import TcyFullInfo, TcyStatus, VNXTcyData, TcyMimirs, TcyEarningsPoint


class TCYInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = deps.cfg.as_interval('tcy.fetch_period', '1h')
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.earnings_points = 28

    VNX_URL_TCY_INFO = 'https://vanaheimex.com/api/tcyInfo'

    async def get_vnx_data(self) -> VNXTcyData:
        async with self.deps.session.get(self.VNX_URL_TCY_INFO) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return VNXTcyData(**data)

    async def get_tcy_status_from_mimir(self) -> TcyStatus:
        mimir = await self.deps.mimir_cache.get_mimir_holder()

        return TcyStatus(
            halt_claiming=mimir.get_constant(TcyMimirs.HALT_CLAIMING),
            halt_staking=mimir.get_constant(TcyMimirs.HALT_STAKING),
            halt_trading=mimir.get_constant(TcyMimirs.HALT_TRADING),
            halt_unstaking=mimir.get_constant(TcyMimirs.HALT_UNSTAKING),
            halt_claiming_swap=mimir.get_constant(TcyMimirs.HALT_CLAIMING_SWAP),
            halt_stake_distribution=mimir.get_constant(TcyMimirs.HALT_STAKE_DISTRIBUTION),
            system_income_bps_to_tcy=mimir.get_constant(TcyMimirs.TCY_STAKE_SYSTEM_INCOME_BPS),
        )

    async def get_tcy_total_supply(self) -> float:
        f = RuneCirculatingSupplyFetcher(self.deps.session, self.deps.thor_connector, self.deps.midgard_connector)
        supplys = await f.get_all_native_token_supplies()
        return f.get_specific_denom_amount(supplys, TCY_DENOM)

    async def get_earnings(self, revenue_bps: int = 1000) -> list[TcyEarningsPoint]:
        earnings = await self.deps.midgard_connector.query_earnings(count=self.earnings_points, interval='day')

        pool_depths = await self.deps.midgard_connector.query_pool_depth_history(
            pool=TCY_SYMBOL,
            interval='day',
            count=self.earnings_points
        )

        tcy_earnings = []
        for day, interval in enumerate(earnings.intervals):
            pool = interval.find_pool(TCY_SYMBOL)
            usd_per_rune = interval.rune_price_usd
            tcy_earnings_rune = thor_to_float(
                interval.liquidity_fees) * revenue_bps / THOR_BASIS_POINT_MAX if pool else 0
            tcy_pool_earnings = thor_to_float(pool.total_liquidity_fees_rune)
            tcy_earnings.append(TcyEarningsPoint(
                timestamp=interval.start_time,
                day_no=day,
                stake_rune=tcy_earnings_rune,
                stake_usd=tcy_earnings_rune * usd_per_rune,
                pool_rune=tcy_pool_earnings,
                pool_usd=tcy_pool_earnings * usd_per_rune,
                tcy_price=pool_depths.intervals[day].asset_price_usd,
            ))
        return tcy_earnings

    async def get_tcy_price_history(self):
        depth_history = await self.deps.midgard_connector.query_pool_depth_history(
            pool=TCY_SYMBOL,
            interval='day',
            count=self.earnings_points
        )
        return [d.asset_price_usd for d in depth_history.intervals]

    async def get_tcy_trade_volume_24h(self) -> float:
        pool_details = await self.deps.midgard_connector.query_pool(TCY_SYMBOL)
        return thor_to_float(pool_details.volume_24h) if pool_details else 0.0

    async def fetch(self) -> TcyFullInfo:
        status = await self.get_tcy_status_from_mimir()
        vnx_data, supply, ph, market, earnings, tcy_trade_volume_24h = await asyncio.gather(
            self.get_vnx_data(),
            self.get_tcy_total_supply(),
            self.deps.pool_cache.get(),
            self.deps.market_info_cache.get(),
            self.get_earnings(status.system_income_bps_to_tcy),
            self.get_tcy_trade_volume_24h()
        )
        ph: PriceHolder

        usd_per_tcy = earnings[-1].tcy_price

        return TcyFullInfo(
            vnx=vnx_data,
            status=status,
            tcy_total_supply=int(supply),
            usd_per_tcy=usd_per_tcy,
            usd_per_rune=market.pool_rune_price,
            rune_market_cap_usd=market.total_supply,
            earnings=earnings,
            tcy_trade_volume_24h=tcy_trade_volume_24h * market.pool_rune_price
        )

    # stake earning = interval.liquidityFees / 1e8 * 10% * runePriceUSD
