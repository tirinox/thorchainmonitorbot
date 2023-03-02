from aiothornode.types import ThorPOL

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer


class POLFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.pol.fetch_period)
        super().__init__(deps, period)

    async def fetch(self) -> ThorPOL:
        pol = await self.deps.thor_connector.query_pol()
        self.logger.info(f"Got POL: {pol}")
        return pol
