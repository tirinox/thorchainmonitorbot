import asyncio
import logging

import aiohttp

from services.config import Config
from services.fetch.price import get_price_of, STABLE_COIN
from services.models.cap_info import ThorInfo, MIDGARD_MULT

NETWORK_URL = "https://chaosnet-midgard.bepswap.com/v1/network"
MIMIR_URL = "https://chaosnet-midgard.bepswap.com/v1/thorchain/mimir"


class CapInfoFetcher:
    SLEEP_PERIOD = 60

    def __init__(self, cfg: Config):
        self.cfg = cfg

    async def fetch_caps(self) -> ThorInfo:
        async with aiohttp.ClientSession() as session:
            try:
                logging.info("start fetching caps and mimir")
                async with session.get(NETWORK_URL) as resp:
                    networks_resp = await resp.json()
                    total_staked = int(networks_resp.get('totalStaked', 0)) * MIDGARD_MULT

                async with session.get(MIMIR_URL) as resp:
                    mimir_resp = await resp.json()
                    max_staked = int(mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1)) * MIDGARD_MULT
                    # max_staked = 900015  # for testing

                price = await get_price_of(session, STABLE_COIN)
                price = 1.0 / price  # Rune/Busd

            except (ValueError, TypeError, IndexError, ZeroDivisionError, KeyError):
                return ThorInfo.error()
            else:
                r = ThorInfo(cap=max_staked, stacked=total_staked, price=price)
                logging.info(r)
                return r

    async def on_got_info(self, info: ThorInfo):
        ...

    async def run(self):
        await asyncio.sleep(3)
        while True:
            new_info = await self.fetch_caps()
            if new_info.is_ok:
                await self.on_got_info(new_info)
            await asyncio.sleep(self.SLEEP_PERIOD)
