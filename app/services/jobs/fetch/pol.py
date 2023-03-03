import asyncio
from typing import List

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.pol import EventPOL
from services.models.pool_member import PoolMemberDetails


class POLFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, reserve_address=None):
        period = parse_timespan_to_seconds(deps.cfg.pol.fetch_period)
        super().__init__(deps, period)
        self.reserve_address = reserve_address or deps.cfg.native_scanner.reserve_address
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)

    async def get_reserve_membership(self, reserve=None) -> List[PoolMemberDetails]:
        reserve = reserve or self.reserve_address
        member_details = await self.deps.midgard_connector.request(
            free_url_gen.url_for_address_pool_membership(reserve))
        details = self.midgard_parser.parse_pool_member_details(member_details, reserve)
        return details

    async def fetch(self) -> EventPOL:
        pol, membership = await asyncio.gather(
            self.deps.thor_connector.query_pol(),
            self.get_reserve_membership(self.reserve_address)
        )
        self.logger.info(f"Got POL: {pol}")
        return EventPOL(
            pol, membership
        )
