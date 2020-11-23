import asyncio
import logging

import aiohttp

from services.fetch.gecko_price import gecko_info
from services.lib.utils import a_result_cached
from services.models.pool_info import MIDGARD_MULT, PoolInfo
from services.models.price import RuneFairPrice, LastPriceHolder


CIRCULATING_SUPPLY_URL = "https://defi.delphidigital.io/chaosnet/int/marketdata"
RUNE_VAULT_BALANCE_URL = "https://defi.delphidigital.io/chaosnet/int/runevaultBalance"


logger = logging.getLogger('fetch_fair_rune_price')


async def delphi_get_rune_vault_balance(session):
    async with session.get(RUNE_VAULT_BALANCE_URL) as resp:
        v = await resp.json()
        return int(v)


async def delphi_get_circulating_supply(session):
    async with session.get(CIRCULATING_SUPPLY_URL) as resp:
        j = await resp.json()
        circulating = int(j['circulating'])
        return circulating


async def fetch_fair_rune_price(price_holder: LastPriceHolder):
    async with aiohttp.ClientSession() as session:
        rune_vault, circulating, gecko = await asyncio.gather(
            delphi_get_rune_vault_balance(session),
            delphi_get_circulating_supply(session),
            gecko_info(session),
        )

        if circulating <= 0:
            raise ValueError(f"circulating is invalid ({circulating})")

        rank = gecko.get('market_cap_rank', 0)

        working_rune = circulating - float(rune_vault)

        if not price_holder.pool_info_map or not price_holder.usd_per_rune:
            raise ValueError(f"pool_info_map is empty!")

        usd_per_rune = price_holder.usd_per_rune

        tlv = 0  # in USD
        for pool in price_holder.pool_info_map.values():
            pool: PoolInfo
            tlv += (pool.balance_rune * MIDGARD_MULT) * usd_per_rune

        fair_price = 3 * tlv / working_rune  # The main formula of wealth!

        result = RuneFairPrice(circulating, rune_vault, usd_per_rune, fair_price, tlv, rank)
        logger.info(result)
        return result


@a_result_cached(ttl=60)
async def fair_rune_price(lph: LastPriceHolder):
    return await fetch_fair_rune_price(lph)
