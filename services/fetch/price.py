import asyncio
import logging
from dataclasses import dataclass

from services.models.cap_info import MIDGARD_MULT
from services.utils import a_result_cached

ASSET_PRICE_URL = "https://chaosnet-midgard.bepswap.com/v1/assets?asset={asset}"
POOL_DETAILS_URL = "https://chaosnet-midgard.bepswap.com/v1/pools/detail?asset={asset}&view=simple"

CIRCULATING_SUPPLY_URL = "https://defi.delphidigital.io/chaosnet/int/marketdata"
RUNE_VAULT_BALANCE_URL = "https://defi.delphidigital.io/chaosnet/int/runevaultBalance"
POOL_LIST_URL = "https://defi.delphidigital.io/chaosnet/thorchain/pools"


STABLE_COIN = "BNB.BUSD-BD1"
BNB_BNB = 'BNB.BNB'


async def get_prices_of(session, asset_list):
    asset_list = ','.join(asset_list)

    price_url = ASSET_PRICE_URL.format(asset=asset_list)
    logging.info(f"loading prices for {asset_list}...")
    async with session.get(price_url) as resp:
        info = await resp.json()
        return {
            pool['asset']: float(pool["priceRune"]) for pool in info
        }


async def get_price_of(session, asset):
    price_map = await get_prices_of(session, [asset])
    return price_map[asset]


@dataclass
class PoolInfo:
    asset: str
    price: float  # runes per 1 asset
    asset_depth: float
    rune_depth: float
    enabled: bool

    @classmethod
    def from_json(cls, j):
        return cls(asset=j['asset'],
                   price=float(j['price']),
                   asset_depth=float(j['assetDepth']) * MIDGARD_MULT,
                   rune_depth=float(j['runeDepth']) * MIDGARD_MULT,
                   enabled=(j['status'] == 'enabled'))

    @classmethod
    def from_json_delphi(cls, j):
        return cls(asset=j['asset'],
                   price=0.0,
                   asset_depth=float(j['balance_asset']) * MIDGARD_MULT,
                   rune_depth=float(j['balance_rune']) * MIDGARD_MULT,
                   enabled=(j['status'] == 'Enabled'))

    @classmethod
    def empty(cls):
        return cls('', None, 0, 0, False)


async def get_pool_info(session, asset_list):
    asset_list = ','.join(asset_list)
    price_url = POOL_DETAILS_URL.format(asset=asset_list)
    logging.info(f"loading pool details for {asset_list}...")
    async with session.get(price_url) as resp:
        pool_list = await resp.json()
        return {
            p['asset']: PoolInfo.from_json(p) for p in pool_list
        }


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
        return [PoolInfo.from_json_delphi(item) for item in j]


@dataclass
class RuneFairPrice:
    circulating: int
    rune_vault_locked: int
    real_rune_price: float
    fair_price: float
    tlv_usd: float


@a_result_cached(ttl=60)
async def fair_rune_price(session):
    pool_info, rune_vault, (circulating, rune_price_usd) = await asyncio.gather(
        delphi_pool_info(session),
        delphi_get_rune_vault_balance(session),
        delphi_get_circulating_supply_and_price_of_rune(session)
    )

    working_rune = circulating - rune_vault

    tlv = 0
    for pool in pool_info:
        pool: PoolInfo
        tlv += pool.rune_depth * rune_price_usd

    fair_price = 3 * tlv / working_rune

    return RuneFairPrice(circulating, rune_vault, rune_price_usd, fair_price, tlv)
