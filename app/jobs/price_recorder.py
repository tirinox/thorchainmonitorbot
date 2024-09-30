import asyncio
import random

from redis import ResponseError
from tqdm import tqdm

from lib.constants import RUNE_SYMBOL_POOL, RUNE_SYMBOL_CEX, RUNE_SYMBOL_DET
from lib.date_utils import DAY, HOUR, MINUTE
from lib.db import DB
from lib.delegates import INotified
from lib.logs import WithLogger
from models.price import RuneMarketInfo
from models.time_series import PriceTimeSeries


class PriceRecorder(WithLogger, INotified):
    async def on_data(self, sender, data: RuneMarketInfo):
        await self.write(data)

    def __init__(self, db: DB, history_max_points: int = 200000):
        super().__init__()
        self.db = db
        self.pool_price_series = PriceTimeSeries(RUNE_SYMBOL_POOL, db, max_len=history_max_points)
        self.cex_price_series = PriceTimeSeries(RUNE_SYMBOL_CEX, db, max_len=history_max_points)
        self.deterministic_price_series = PriceTimeSeries(RUNE_SYMBOL_DET, db, max_len=history_max_points)

    async def write(self, rune_market_info: RuneMarketInfo):
        if not rune_market_info:
            self.logger.error('No rune_market_info!')
            return

        # if self.deps.price_holder:
        #     rune_market_info.pool_rune_price = self.deps.price_holder.usd_per_rune

        # Pool price fill
        if rune_market_info.pool_rune_price and rune_market_info.pool_rune_price > 0:
            await self.pool_price_series.add(price=rune_market_info.pool_rune_price)
        else:
            self.logger.error(f'Odd {rune_market_info.pool_rune_price = }')

        # CEX price fill
        if rune_market_info.cex_price and rune_market_info.cex_price > 0:
            await self.cex_price_series.add(price=rune_market_info.cex_price)
        else:
            self.logger.error(f'Odd {rune_market_info.cex_price = }')

        # Deterministic price fill
        if rune_market_info.fair_price and rune_market_info.fair_price > 0:
            await self.deterministic_price_series.add(price=rune_market_info.fair_price)
        else:
            self.logger.error(f'Odd {rune_market_info.fair_price = }')

    async def get_prices(self, period, max_points=None):
        if not max_points:
            max_points = 60_000 if period >= 7 * DAY else 10_000

        pool_prices = await self.pool_price_series.get_last_values(period, with_ts=True, max_points=max_points)
        cex_prices = await self.cex_price_series.get_last_values(period, with_ts=True, max_points=max_points)
        det_prices = await self.deterministic_price_series.get_last_values(period, with_ts=True, max_points=max_points)

        return pool_prices, cex_prices, det_prices

    async def historical_get_triplet(self):
        price_1h, price_24h, price_7d = await asyncio.gather(
            self.pool_price_series.select_average_ago(HOUR, tolerance=MINUTE * 7),
            self.pool_price_series.select_average_ago(DAY, tolerance=MINUTE * 40),
            self.pool_price_series.select_average_ago(DAY * 7, tolerance=HOUR * 2)
        )
        return price_1h, price_24h, price_7d

    async def dbg_fill_rune_price_external(self, price_chart, include_fake_det=False):
        self.logger.warning('fill_rune_price_from_gecko is called!')

        if not price_chart:
            self.logger.error('no gecko data!')
            return

        price_chart.sort(key=lambda p: p[0])

        await self.deterministic_price_series.clear()
        await self.cex_price_series.clear()

        if include_fake_det:
            await self.deterministic_price_series.clear()

        for ts, price in tqdm(price_chart):
            ident = f'{ts}-0'
            try:
                await self.pool_price_series.add(message_id=ident, price=price)
                cex_price = price * random.uniform(0.95, 1.05)
                await self.cex_price_series.add(message_id=ident, price=cex_price)
                if include_fake_det:
                    det_price = price / random.uniform(2.8, 3.1)
                    await self.deterministic_price_series.add(message_id=ident, price=det_price)
            except ResponseError:
                self.logger.error('ResponseError while adding price')

    @staticmethod
    async def purge_spike_time_series(series: PriceTimeSeries, interval, max_value):
        points = await series.get_last_points(interval, 1_000_000)
        message_ids = [p[0] for p in points if float(p[1]['price']) > max_value]
        print(f'Bad points for {series.stream_name} are {len(message_ids)} of total {len(points)}')

        r = series.db.redis
        if message_ids:
            await r.xdel(series.stream_name, *message_ids)

    async def purge_spikes(self, interval, max_value_pool, max_value_det):
        await self.purge_spike_time_series(self.deterministic_price_series, interval, max_value_det)
        await self.purge_spike_time_series(self.pool_price_series, interval, max_value_pool)
