import asyncio
import logging

import aiohttp

from services.jobs.fetch.gecko_price import gecko_info
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.utils import a_result_cached
from services.models.pool_info import PoolInfo
from services.models.price import RuneFairPrice, LastPriceHolder

CIRCULATING_SUPPLY_URL = "https://defi.delphidigital.io/chaosnet/int/marketdata"
RUNE_VAULT_BALANCE_URL = "https://defi.delphidigital.io/chaosnet/int/runevaultBalance"

MIDGARD_BEP2_STATS_URL = 'https://chaosnet-midgard.bepswap.com/v1/network'
MIDGARD_MCCN_STATS_URL = 'https://midgard.thorchain.info/v2/network'

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


async def total_pooled_rune(session, network_stats_url):
    async with session.get(network_stats_url) as resp:
        j = await resp.json()
        total_pooled_rune = int(j.get('totalStaked', 0))
        if not total_pooled_rune:
            total_pooled_rune = int(j.get('totalPooledRune', 0))
        total_pooled_rune *= THOR_DIVIDER_INV
        return total_pooled_rune


async def total_locked_value_all_networks(session):
    tlv_bepswap, tlv_mccn = await asyncio.gather(
        total_pooled_rune(session, MIDGARD_BEP2_STATS_URL),
        total_pooled_rune(session, MIDGARD_MCCN_STATS_URL)
    )
    return tlv_mccn + tlv_bepswap


async def fetch_fair_rune_price(price_holder: LastPriceHolder):
    async with aiohttp.ClientSession() as session:
        rune_vault, circulating, gecko, total_locked_rune = await asyncio.gather(
            delphi_get_rune_vault_balance(session),
            delphi_get_circulating_supply(session),
            gecko_info(session),
            total_locked_value_all_networks(session)
        )

        if circulating <= 0:
            raise ValueError(f"circulating is invalid ({circulating})")

        rank = gecko.get('market_cap_rank', 0)

        working_rune = circulating - float(rune_vault)

        if not price_holder.pool_info_map or not price_holder.usd_per_rune:
            raise ValueError(f"pool_info_map is empty!")

        tlv = total_locked_rune * price_holder.usd_per_rune  # == tlv of non-rune assets

        fair_price = 3 * tlv / working_rune  # The main formula of wealth!

        result = RuneFairPrice(circulating, rune_vault, price_holder.usd_per_rune, fair_price, tlv, rank)
        logger.info(result)
        return result


@a_result_cached(ttl=60)
async def fair_rune_price(lph: LastPriceHolder):
    return await fetch_fair_rune_price(lph)
