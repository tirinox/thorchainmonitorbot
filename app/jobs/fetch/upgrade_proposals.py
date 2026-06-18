from typing import List

from api.aionode.types import ThorUpgradeProposal
from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer


class UpgradeProposalsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.upgrade_proposals.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> List[ThorUpgradeProposal]:
        proposals = await self.deps.thor_connector.query_upgrade_proposals()
        self.deps.upgrade_proposals = proposals
        return proposals

