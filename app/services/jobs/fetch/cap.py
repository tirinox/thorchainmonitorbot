from services.jobs.fetch.base import BaseFetcher
from services.jobs.midgard import get_midgard_url
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.cap_info import ThorCapInfo


class CapInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher):
        self.ppf = ppf
        sleep_period = parse_timespan_to_seconds(deps.cfg.cap.fetch_period)
        super().__init__(deps, sleep_period)

    def url_mimir(self):
        return get_midgard_url(self.deps.cfg, '/thorchain/mimir')

    def url_network(self):
        return get_midgard_url(self.deps.cfg, '/network')

    async def fetch(self) -> ThorCapInfo:
        self.logger.info("start fetching caps and mimir")

        session = self.deps.session

        async with session.get(self.url_network()) as resp:
            networks_resp = await resp.json()
            if 'totalStaked' in networks_resp:
                total_staked = networks_resp.get('totalStaked', 0)
            else:
                total_staked = networks_resp.get('totalPooledRune', 0)

            total_staked = int(total_staked) * THOR_DIVIDER_INV

        async with session.get(self.url_mimir()) as resp:
            mimir_resp = await resp.json()
            max_staked = int(mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1)) * THOR_DIVIDER_INV

            # max_staked = 90_000_015  # for testing

        if max_staked <= 1:
            self.logger.error(f"max_staked = {max_staked} and total_staked = {total_staked} which seems like an error")
            return ThorCapInfo.error()

        price = self.deps.price_holder.usd_per_rune

        r = ThorCapInfo(cap=max_staked, stacked=total_staked, price=price)
        self.logger.info(f"ThorInfo got the following {r}")
        return r
