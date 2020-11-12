import aiohttp

from services.fetch.base import BaseFetcher
from services.fetch.price import get_price_of, STABLE_COIN
from services.models.cap_info import ThorInfo, MIDGARD_MULT

NETWORK_URL = "https://chaosnet-midgard.bepswap.com/v1/network"
MIMIR_URL = "https://chaosnet-midgard.bepswap.com/v1/thorchain/mimir"


class CapInfoFetcher(BaseFetcher):
    async def fetch(self) -> ThorInfo:
        async with aiohttp.ClientSession() as session:
            self.logger.info("start fetching caps and mimir")
            async with session.get(NETWORK_URL) as resp:
                networks_resp = await resp.json()
                total_staked = int(networks_resp.get('totalStaked', 0)) * MIDGARD_MULT

            async with session.get(MIMIR_URL) as resp:
                mimir_resp = await resp.json()
                max_staked = int(mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1)) * MIDGARD_MULT

                # max_staked = 900015  # for testing

            price = await get_price_of(session, STABLE_COIN)
            price = 1.0 / price  # Rune/Busd

            r = ThorInfo(cap=max_staked, stacked=total_staked, price=price)
            self.logger.info(f"ThorInfo got the following {r}")
            return r
