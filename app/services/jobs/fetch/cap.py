from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.date_utils import parse_timespan_to_seconds
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
        session = self.deps.session
        url_network = self.url_gen.url_network()
        self.logger.info(f"get network: {url_network}")
        async with session.get(url_network) as resp:
            networks_resp = await resp.json()
            if 'totalStaked' in networks_resp:
                total_staked = networks_resp.get('totalStaked', 0)
            else:
                total_staked = networks_resp.get('totalPooledRune', 0)

            total_staked = int(total_staked) * THOR_DIVIDER_INV

        url_mimir = self.url_gen.url_mimir()
        self.logger.info(f"get mimir: {url_network}")
        async with session.get(url_mimir) as resp:
            mimir_resp = await resp.json()
            if 'mimir//MAXLIQUIDITYRUNE' in mimir_resp:
                max_staked_str = mimir_resp.get("mimir//MAXLIQUIDITYRUNE", 1)
            else:
                max_staked_str = mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1)

            max_staked = int(max_staked_str) * THOR_DIVIDER_INV

            # max_staked = 200_000  # for testing

        if max_staked <= 1:
            self.logger.error(f"max_staked = {max_staked} and total_staked = {total_staked} which seems like an error")
            return ThorCapInfo.error()

        price = self.deps.price_holder.usd_per_rune

        r = ThorCapInfo(cap=max_staked, stacked=total_staked, price=price)
        self.logger.info(f"ThorInfo got the following {r}")
        return r
