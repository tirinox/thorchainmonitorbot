import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.cap_info import ThorCapInfo


class CapInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.cap.fetch_period)
        super().__init__(deps, sleep_period)
        self.url_gen = get_url_gen_by_network_id(deps.cfg.network_id)
        self.last_network_info = {}
        self.last_mimir = {}

    MIMIR_CAP_KEYS = [
        'mimir//MAXLIQUIDITYRUNE',
        "mimir//MAXIMUMLIQUIDITYRUNE",
        "mimir//MAXIMUMSTAKERUNE"
    ]

    async def get_constants(self):
        session = self.deps.session
        url_network = self.url_gen.url_network()
        self.logger.info(f"get network: {url_network}")
        async with session.get(url_network) as resp:
            self.last_network_info = await resp.json()
            return self.last_network_info

    async def get_mimir(self):
        url_mimir = self.url_gen.url_mimir()
        self.logger.info(f"get mimir: {url_mimir}")
        async with self.deps.session.get(url_mimir) as resp:
            self.last_mimir = await resp.json()
            return self.last_mimir

    async def get_total_current_pooled_rune(self):
        networks_resp = await self.get_constants()

        if 'totalStaked' in networks_resp:
            lp_rune = networks_resp.get('totalStaked', 0)
        else:
            lp_rune = networks_resp.get('totalPooledRune', 0)

        return int(lp_rune) * THOR_DIVIDER_INV

    async def get_max_possible_pooled_rune(self):
        mimir_resp = await self.get_mimir()

        for key in self.MIMIR_CAP_KEYS:
            if key in mimir_resp:
                return int(mimir_resp[key]) * THOR_DIVIDER_INV
        return 1e-8

    async def fetch(self) -> ThorCapInfo:
        max_lp_rune, current_lp_rune = await asyncio.gather(
            self.get_max_possible_pooled_rune(),
            self.get_total_current_pooled_rune()
        )

        # max_lp_rune = 2_003_000  # fixme: debug!! for testing

        if max_lp_rune <= 1 or current_lp_rune < 0:
            self.logger.error(f"{max_lp_rune = } and {current_lp_rune = } which seems like an error")
            return ThorCapInfo.error()

        price = self.deps.price_holder.usd_per_rune

        r = ThorCapInfo(cap=max_lp_rune, pooled_rune=current_lp_rune, price=price)
        self.logger.info(f"ThorInfo got the following {r}")
        return r
