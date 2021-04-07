from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.cap_info import ThorCapInfo


class CapInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher):
        self.ppf = ppf
        sleep_period = parse_timespan_to_seconds(deps.cfg.cap.fetch_period)
        super().__init__(deps, sleep_period)
        self.url_gen = get_url_gen_by_network_id(deps.cfg.network_id)

    async def fetch(self) -> ThorCapInfo:
        self.logger.info("start fetching caps and mimir")

        session = self.deps.session

        async with session.get(self.url_gen.url_network()) as resp:
            networks_resp = await resp.json()
            if 'totalStaked' in networks_resp:
                total_staked = networks_resp.get('totalStaked', 0)
            else:
                total_staked = networks_resp.get('totalPooledRune', 0)

            total_staked = int(total_staked) * THOR_DIVIDER_INV

        async with session.get(self.url_gen.url_mimir()) as resp:
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
