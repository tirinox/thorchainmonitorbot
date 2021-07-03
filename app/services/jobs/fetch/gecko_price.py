import logging

import aiohttp
from aioredis import ReplyError
from tqdm import tqdm

from services.lib.constants import RUNE_SYMBOL_DET, RUNE_SYMBOL_MARKET
from services.models.time_series import PriceTimeSeries

COIN_CHART_GECKO = "https://api.coingecko.com/api/v3/coins/thorchain/market_chart?vs_currency=usd&days={days}"
COIN_RANK_GECKO = "https://api.coingecko.com/api/v3/coins/thorchain?" \
                  "tickers=true&market_data=true&community_data=false&developer_data=false"


async def get_rune_chart(days):
    async with aiohttp.ClientSession() as session:
        async with session.get(COIN_CHART_GECKO.format(days=days)) as resp:
            j = await resp.json()
            return j['prices']


async def fill_rune_price_from_gecko(db, include_fake_det=False, fake_value=0.2):
    logging.warning('fill_rune_price_from_gecko is called!')
    gecko_data8 = await get_rune_chart(8)
    gecko_data1 = await get_rune_chart(1)

    price_chart = gecko_data8 + gecko_data1
    price_chart.sort(key=lambda p: p[0])

    series = PriceTimeSeries(RUNE_SYMBOL_MARKET, db)
    await series.clear()

    det_series = PriceTimeSeries(RUNE_SYMBOL_DET, db)
    if include_fake_det:
        await det_series.clear()

    for ts, price in tqdm(price_chart):
        ident = f'{ts}-0'
        try:
            await series.add(message_id=ident, price=price)
            if include_fake_det:
                await det_series.add(message_id=ident, price=fake_value)
        except ReplyError:
            pass


async def get_thorchain_coin_gecko_info(session):
    async with session.get(COIN_RANK_GECKO) as resp:
        j = await resp.json()
        return j


def gecko_market_cap_rank(gecko_json):
    return gecko_json.get('market_cap_rank', 0) if gecko_json else 0


def gecko_ticker_price(gecko_json, exchange='binance', base_curr='USDT'):
    tickers = gecko_json.get('tickers', [])
    for t in tickers:
        this_base_curr = t.get('target')
        this_exchange = t.get('market', {}).get('identifier')
        if this_exchange == exchange and this_base_curr == base_curr:
            return float(t.get('last', 0))
