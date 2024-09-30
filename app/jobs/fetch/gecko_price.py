import logging

import aiohttp
from aiohttp import ContentTypeError

from jobs.price_recorder import PriceRecorder

COIN_CHART_GECKO = "https://api.coingecko.com/api/v3/coins/thorchain/market_chart?vs_currency=usd&days={days}"
COIN_RANK_GECKO = "https://api.coingecko.com/api/v3/coins/thorchain?" \
                  "market_data=true&community_data=false&developer_data=false"

GECKO_TIMEOUT = aiohttp.ClientTimeout(total=25)  # sec


async def get_gecko_rune_chart(days):
    async with aiohttp.ClientSession() as session:
        async with session.get(COIN_CHART_GECKO.format(days=days), timeout=GECKO_TIMEOUT) as resp:
            j = await resp.json()
            return j['prices']


async def fill_rune_price_from_gecko(db, include_fake_det=False, fake_value=0.2):
    logging.warning('fill_rune_price_from_gecko is called!')
    gecko_data8 = await get_gecko_rune_chart(8)
    gecko_data1 = await get_gecko_rune_chart(1)

    if not gecko_data1 or not gecko_data8:
        logging.error('no gecko data!')
        return

    price_chart = gecko_data8 + gecko_data1

    price_recorder = PriceRecorder(db)
    await price_recorder.dbg_fill_rune_price_external(price_chart, include_fake_det)


async def get_thorchain_coin_gecko_info(session):
    try:
        async with session.get(COIN_RANK_GECKO, timeout=GECKO_TIMEOUT) as resp:
            j = await resp.json()
            return j
    except ContentTypeError as e:
        logging.error(f'Error while fetching gecko info: {e}')


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
