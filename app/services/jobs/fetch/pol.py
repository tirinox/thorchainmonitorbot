from typing import List

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.pol import AlertPOL, POLState
from services.models.pool_member import PoolMemberDetails


class RunePoolFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, reserve_address=None):
        period = parse_timespan_to_seconds(deps.cfg.pol.fetch_period)
        super().__init__(deps, period)
        self.reserve_address = reserve_address or deps.cfg.native_scanner.reserve_address
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)

    async def get_reserve_membership(self, reserve=None) -> List[PoolMemberDetails]:
        reserve = reserve or self.reserve_address
        member_details = await self.deps.midgard_connector.request(
            free_url_gen.url_for_address_pool_membership(reserve))

        if not member_details:
            self.logger.warning(f'Reserve address is not member of pools')
            return []

        details = self.midgard_parser.parse_pool_member_details(member_details, reserve)
        details.sort(key=lambda d: d.pool)
        return details

    async def fetch(self) -> AlertPOL:
        runepool = await self.deps.thor_connector.query_runepool()

        if runepool.pol.value > 0:
            membership = await self.get_reserve_membership(self.reserve_address)
        else:
            membership = []

        self.logger.info(f"Got RunePOOL: {runepool}")
        return AlertPOL(
            POLState(self.deps.price_holder.usd_per_rune, runepool),
            membership
        )
