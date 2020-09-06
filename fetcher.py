import asyncio
import logging

import aiohttp
from config import Config
from model import ThorInfo


class InfoFetcher:
    SLEEP_PERIOD = 30
    MULT = 10 ** -8

    def __init__(self, cfg: Config):
        self.cfg = cfg

    async def fetch_caps(self) -> ThorInfo:
        urls = self.cfg.thorchain.chaosnet.urls

        async with aiohttp.ClientSession() as session:
            try:
                logging.info("start fetching")
                async with session.get(urls.network) as resp:
                    networks_resp = await resp.json()
                    total_staked = int(networks_resp.get('totalStaked', 0)) * self.MULT

                async with session.get(urls.mimir) as resp:
                    mimir_resp = await resp.json()
                    max_staked = int(mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1)) * self.MULT
                    # max_staked = 900012

                async with session.get(urls.busd_to_rune) as resp:
                    busd = await resp.json()
                    price = 1.0 / float(busd[0]["priceRune"])

            except (ValueError, TypeError, IndexError):
                return ThorInfo.zero()
            else:
                r = ThorInfo(cap=max_staked, stacked=total_staked, price=price)
                logging.info(r)
                return r

    async def on_got_info(self, info: ThorInfo):
        ...

    async def fetch_loop(self):
        await asyncio.sleep(3)
        while True:
            new_info = await self.fetch_caps()
            await self.on_got_info(new_info)
            await asyncio.sleep(self.SLEEP_PERIOD)
