from services.fetch.base import BaseFetcher
from services.fetch.pool_price import MIDGARD_MULT, PoolPriceFetcher, BUSD_SYMBOL

from services.models.cap_info import ThorInfo

NETWORK_URL = "https://chaosnet-midgard.bepswap.com/v1/network"
MIMIR_URL = "https://chaosnet-midgard.bepswap.com/v1/thorchain/mimir"


class CapInfoFetcher(BaseFetcher):
    async def fetch(self) -> ThorInfo:
        self.logger.info("start fetching caps and mimir")
        async with self.session.get(NETWORK_URL) as resp:
            networks_resp = await resp.json()
            total_staked = int(networks_resp.get('totalStaked', 0)) * MIDGARD_MULT

        async with self.session.get(MIMIR_URL) as resp:
            mimir_resp = await resp.json()
            max_staked = int(mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1)) * MIDGARD_MULT

            # max_staked = 900015  # for testing

        ppf = PoolPriceFetcher(session=self.session)
        price = await ppf.get_price_in_rune(BUSD_SYMBOL)

        r = ThorInfo(cap=max_staked, stacked=total_staked, price=price)
        self.logger.info(f"ThorInfo got the following {r}")
        return r
