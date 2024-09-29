from jobs.fetch.base import BaseFetcher
from lib.constants import thor_to_float
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from lib.midgard.urlgen import free_url_gen
from lib.thor_logic import get_effective_security_bond
from models.cap_info import ThorCapInfo


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
        self.last_network_info = await self.deps.midgard_connector.request(free_url_gen.url_network())
        return self.last_network_info

    async def get_total_current_pooled_rune_and_cap(self):
        networks_resp = await self.get_network_info()
        lp_rune = networks_resp.get('totalPooledRune', 0)
        bonds = networks_resp.get('activeBonds', [])
        cap_eq_bond = get_effective_security_bond(bonds)
        return (
            int(thor_to_float(lp_rune)),
            int(thor_to_float(cap_eq_bond))
        )

    async def fetch(self) -> ThorCapInfo:
        current_lp_rune, max_lp_rune = await self.get_total_current_pooled_rune_and_cap()

        # max_lp_rune = 16_500_000  # fixme: debug!! for testing
        # current_lp_rune = 15_500_000  # fixme: debug!! for testing

        if max_lp_rune <= 1 or current_lp_rune < 0:
            return ThorCapInfo.error()

        price = self.deps.price_holder.usd_per_rune

        r = ThorCapInfo(
            cap=int(max_lp_rune),
            pooled_rune=current_lp_rune,
            price=price
        )
        self.logger.info(f"ThorInfo got the following {r}")
        return r
