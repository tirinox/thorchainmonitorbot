import logging
import random

import aiohttp
import aioredis
from tqdm import tqdm

from services.lib.constants import RUNE_SYMBOL_DET, RUNE_SYMBOL_POOL, RUNE_SYMBOL_CEX
from services.models.time_series import PriceTimeSeries

COIN_CHART_GECKO = "https://api.coingecko.com/api/v3/coins/thorchain/market_chart?vs_currency=usd&days={days}"
COIN_RANK_GECKO = "https://api.coingecko.com/api/v3/coins/thorchain?" \
                  "market_data=true&community_data=false&developer_data=false"

GECKO_TIMEOUT = aiohttp.ClientTimeout(total=25)  # sec


async def get_rune_chart(days):
    async with aiohttp.ClientSession() as session:
        async with session.get(COIN_CHART_GECKO.format(days=days), timeout=GECKO_TIMEOUT) as resp:
            j = await resp.json()
            return j['prices']


async def fill_rune_price_from_gecko(db, include_fake_det=False, fake_value=0.2):
    logging.warning('fill_rune_price_from_gecko is called!')
    gecko_data8 = await get_rune_chart(8)
    gecko_data1 = await get_rune_chart(1)

    if not gecko_data1 or not gecko_data8:
        logging.error('no gecko data!')
        return

    price_chart = gecko_data8 + gecko_data1
    price_chart.sort(key=lambda p: p[0])

    series = PriceTimeSeries(RUNE_SYMBOL_POOL, db)
    await series.clear()

    cex_series = PriceTimeSeries(RUNE_SYMBOL_CEX, db)
    await cex_series.clear()

    det_series = PriceTimeSeries(RUNE_SYMBOL_DET, db)
    if include_fake_det:
        await det_series.clear()

    for ts, price in tqdm(price_chart):
        ident = f'{ts}-0'
        try:
            await series.add(message_id=ident, price=price)
            cex_price = price * random.uniform(0.95, 1.05)
            await cex_series.add(message_id=ident, price=cex_price)
            if include_fake_det:
                det_price = price / random.uniform(2.8, 3.1)
                await det_series.add(message_id=ident, price=det_price)
        except aioredis.ResponseError:
            pass


async def get_thorchain_coin_gecko_info(session):
    async with session.get(COIN_RANK_GECKO, timeout=GECKO_TIMEOUT) as resp:
        j = await resp.json()
        return j


def gecko_market_cap_rank(gecko_json):
    return gecko_json.get('market_cap_rank', 0) if gecko_json else 0


def gecko_ticker_price(gecko_json, exchange='binance', base_curr='USDT'):
    tickers = gecko_json.get('tickers', [])
    base_curr = base_curr.lower()
    exchange = exchange.lower()
    for t in tickers:
        this_base_curr = t.get('target', '').lower()
        this_exchange = t.get('market', {}).get('identifier', '').lower()
        if this_exchange == exchange and this_base_curr == base_curr:
            return float(t.get('last', 0))


def gecko_market_volume(gecko_json):
    return float(gecko_json.get('market_data', {}).get('total_volume', {}).get('usd', 0.0))
