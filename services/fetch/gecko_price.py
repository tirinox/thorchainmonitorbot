import aiohttp
from tqdm import tqdm

from services.fetch.pool_price import RUNE_SYMBOL
from services.models.time_series import PriceTimeSeries

COIN_CHART_GECKO = "https://api.coingecko.com/api/v3/coins/thorchain/market_chart?vs_currency=usd&days={days}"


async def get_rune_chart(days):
    async with aiohttp.ClientSession() as session:
        async with session.get(COIN_CHART_GECKO.format(days=days)) as resp:
            j = await resp.json()
            return j['prices']


async def fill_rune_price_from_gecko(db):
    gecko_data8 = await get_rune_chart(8)
    gecko_data1 = await get_rune_chart(1)

    price_chart = gecko_data8 + gecko_data1
    price_chart.sort(key=lambda p: p[0])

    series = PriceTimeSeries(RUNE_SYMBOL, db)
    await series.clear()

    for ts, price in tqdm(price_chart):
        ident = f'{ts}-0'
        await series.add(message_id=ident, price=price)
