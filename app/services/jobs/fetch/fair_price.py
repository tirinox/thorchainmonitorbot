import asyncio
import logging

import aiohttp

from services.jobs.fetch.gecko_price import get_thorchain_coin_gecko_info, gecko_market_cap_rank, gecko_ticker_price, \
    gecko_market_volume
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.midgard.connector import MidgardConnector
from services.lib.midgard.urlgen import free_url_gen
from services.lib.utils import a_result_cached
from services.models.price import RuneMarketInfo, LastPriceHolder

logger = logging.getLogger('fetch_fair_rune_price')


async def total_locked_value_all_networks(midgard: MidgardConnector):
    j = await midgard.request_random_midgard(free_url_gen.url_network())
    total_pooled_rune = int(j.get('totalStaked', 0))
    if not total_pooled_rune:
        total_pooled_rune = int(j.get('totalPooledRune', 0))
    total_pooled_rune *= THOR_DIVIDER_INV
    return total_pooled_rune


async def fetch_fair_rune_price(price_holder: LastPriceHolder, midgard: MidgardConnector) -> RuneMarketInfo:
    rune_vault = 0
    gecko, total_locked_rune = await asyncio.gather(
        get_thorchain_coin_gecko_info(midgard.session),
        total_locked_value_all_networks(midgard)
    )

    circulating = int(gecko['market_data']['circulating_supply'])

    if circulating <= 0:
        raise ValueError(f"circulating is invalid ({circulating})")

    working_rune = circulating - float(rune_vault)

    if not price_holder.pool_info_map or not price_holder.usd_per_rune:
        raise ValueError(f"pool_info_map is empty!")

    tlv = total_locked_rune * price_holder.usd_per_rune  # == tlv of non-rune assets

    fair_price = 3 * tlv / working_rune  # The main formula of wealth!

    cex_price = gecko_ticker_price(gecko, 'binance', 'USDT')  # RUNE/USDT @ Binance
    rank = gecko_market_cap_rank(gecko)
    trade_volume = gecko_market_volume(gecko)

    result = RuneMarketInfo(circulating=circulating,
                            rune_vault_locked=rune_vault,
                            pool_rune_price=price_holder.usd_per_rune,
                            fair_price=fair_price,
                            cex_price=cex_price,
                            tlv_usd=tlv,
                            rank=rank,
                            total_trade_volume_usd=trade_volume)
    logger.info(result)
    return result


@a_result_cached(ttl=60)
async def get_fair_rune_price_cached(lph: LastPriceHolder, midgard: MidgardConnector) -> RuneMarketInfo:
    return await fetch_fair_rune_price(lph, midgard)
