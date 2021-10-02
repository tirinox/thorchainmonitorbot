import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import thor_to_float
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import free_url_gen
from services.models.cap_info import ThorCapInfo


class CapInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.cap.fetch_period)
        super().__init__(deps, sleep_period)
        self.last_network_info = {}
        self.last_mimir = {}

    MIMIR_CAP_KEYS = [
        "mimir//MAXIMUMLIQUIDITYRUNE",  # order
        'mimir//MAXLIQUIDITYRUNE',
        "mimir//MAXIMUMSTAKERUNE"
    ]

    async def get_network_info(self):
        self.last_network_info = await self.deps.midgard_connector.request_random_midgard(free_url_gen.url_network())
        return self.last_network_info

    async def get_mimir(self):
        self.last_mimir = await self.deps.midgard_connector.request_random_midgard(free_url_gen.url_mimir())
        return self.last_mimir

    async def get_total_current_pooled_rune(self):
        networks_resp = await self.get_network_info()

        if 'totalStaked' in networks_resp:
            lp_rune = networks_resp.get('totalStaked', 0)
        else:
            lp_rune = networks_resp.get('totalPooledRune', 0)

        return thor_to_float(lp_rune)

    async def get_max_possible_pooled_rune(self):
        mimir_resp = await self.get_mimir()

        for key in self.MIMIR_CAP_KEYS:
            if key in mimir_resp:
                return thor_to_float(mimir_resp[key])
        return 1e-8

    async def fetch(self) -> ThorCapInfo:
        max_lp_rune, current_lp_rune = await asyncio.gather(
            self.get_max_possible_pooled_rune(),
            self.get_total_current_pooled_rune()
        )

        # max_lp_rune = 5_801_000  # fixme: debug!! for testing
        # current_lp_rune = 5_799_000  # fixme: debug!! for testing

        if max_lp_rune <= 1 or current_lp_rune < 0:
            self.logger.error(f"{max_lp_rune = } and {current_lp_rune = } which seems like an error")
            return ThorCapInfo.error()

        price = self.deps.price_holder.usd_per_rune

        r = ThorCapInfo(cap=max_lp_rune, pooled_rune=current_lp_rune, price=price)
        self.logger.info(f"ThorInfo got the following {r}")
        return r
