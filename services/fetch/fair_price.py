import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from services.models.pool_info import MIDGARD_MULT, PoolInfo
from services.utils import a_result_cached

CIRCULATING_SUPPLY_URL = "https://defi.delphidigital.io/chaosnet/int/marketdata"
RUNE_VAULT_BALANCE_URL = "https://defi.delphidigital.io/chaosnet/int/runevaultBalance"
POOL_LIST_URL = "https://defi.delphidigital.io/chaosnet/thorchain/pools"


async def delphi_get_rune_vault_balance(session):
    async with session.get(RUNE_VAULT_BALANCE_URL) as resp:
        v = await resp.json()
        return int(v)


async def delphi_get_circulating_supply_and_price_of_rune(session):
    async with session.get(CIRCULATING_SUPPLY_URL) as resp:
        j = await resp.json()
        rune_price_usd = float(j['priceUsd'])
        circulating = int(j['circulating'])
        return circulating, rune_price_usd


async def delphi_pool_info(session):
    async with session.get(POOL_LIST_URL) as resp:
        j = await resp.json()
        return [PoolInfo.from_dict(item) for item in j]


@dataclass
class RuneFairPrice:
    circulating: int
    rune_vault_locked: int
    real_rune_price: float
    fair_price: float
    tlv_usd: float


async def fetch_fair_rune_price():
    async with aiohttp.ClientSession() as session:
        pool_info, rune_vault, (circulating, rune_price_usd) = await asyncio.gather(
            delphi_pool_info(session),
            delphi_get_rune_vault_balance(session),
            delphi_get_circulating_supply_and_price_of_rune(session)
        )

        working_rune = circulating - rune_vault

        tlv = 0
        for pool in pool_info:
            pool: PoolInfo
            tlv += (pool.balance_rune * MIDGARD_MULT) * rune_price_usd

        fair_price = 3 * tlv / working_rune  # The main formula of wealth!

        logging.info(f"fetch_fair_rune_price: tlv = ${int(tlv)}, "
                     f"circulating = R {int(circulating)}, "
                     f"rune vault = R {int(rune_vault)}, "
                     f"rune price = ${rune_price_usd:.3f}")

        return RuneFairPrice(circulating, rune_vault, rune_price_usd, fair_price, tlv)


@a_result_cached(ttl=60)
async def fair_rune_price():
    return await fetch_fair_rune_price()
