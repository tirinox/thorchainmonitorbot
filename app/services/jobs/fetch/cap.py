from typing import List

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
        "MAXIMUMLIQUIDITYRUNE",  # order
        'MAXLIQUIDITYRUNE',
        "MAXIMUMSTAKERUNE"
    ]

    async def get_network_info(self):
        self.last_network_info = await self.deps.midgard_connector.request_random_midgard(free_url_gen.url_network())
        return self.last_network_info

    async def get_mimir(self):
        self.last_mimir = await self.deps.midgard_connector.request_random_midgard(free_url_gen.url_mimir())
        return self.last_mimir

    @staticmethod
    def calculate_effective_security_bond(node_bonds: List[int]):
        node_bonds.sort()
        t = len(node_bonds) * 2 // 3
        if len(node_bonds) % 3 == 0:
            t -= 1

        amt = 0
        for i, bond in enumerate(node_bonds):
            if i <= t:
                amt += thor_to_float(bond)
            else:
                break
        return amt

    async def get_total_current_pooled_rune_and_cap(self):
        networks_resp = await self.get_network_info()
        lp_rune = networks_resp.get('totalPooledRune', 0)
        bonds = networks_resp.get('activeBonds', [])
        cap_eq_bond = self.calculate_effective_security_bond(bonds)
        return int(thor_to_float(lp_rune)), cap_eq_bond

    async def get_max_possible_pooled_rune(self):
        mimir_resp = await self.get_mimir()

        for key in self.MIMIR_CAP_KEYS:
            if key in mimir_resp:
                return thor_to_float(mimir_resp[key])
        return 1e-8

    async def fetch(self) -> ThorCapInfo:
        current_lp_rune, max_lp_rune = await self.get_total_current_pooled_rune_and_cap()

        # max_lp_rune = 16_500_000  # fixme: debug!! for testing
        # current_lp_rune = 15_500_000  # fixme: debug!! for testing

        if max_lp_rune <= 1 or current_lp_rune < 0:
            self.logger.error(f"{max_lp_rune = } and {current_lp_rune = } which seems like an error")
            return ThorCapInfo.error()

        price = self.deps.price_holder.usd_per_rune

        r = ThorCapInfo(cap=max_lp_rune, pooled_rune=current_lp_rune, price=price)
        self.logger.info(f"ThorInfo got the following {r}")
        return r
