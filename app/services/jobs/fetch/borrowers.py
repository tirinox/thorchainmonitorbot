import datetime
from typing import List, Optional

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.flipside import FlipSideConnector
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.loans import LendingStats

URL_FS_BORROWERS_V1 = 'https://api.flipsidecrypto.com/api/v2/queries/1052d5a2-db2b-4847-9cea-955af435ae13/data/latest'
URL_FS_BORROWERS_V2 = 'https://api.flipsidecrypto.com/api/v2/queries/36061d26-2d54-4239-bbf0-490aac83bed9/data/latest'
URL_FS_BORROWERS = URL_FS_BORROWERS_V2

MAX_AGE_TO_REPORT_ERROR = 3 * DAY


class BorrowersFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.borrowers.fetch_period)
        super().__init__(deps, period)
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.fs = FlipSideConnector(deps.session)

    async def get_borrower_list(self) -> List[str]:
        borrowers = await self.deps.midgard_connector.request(free_url_gen.url_borrowers())

        if not borrowers:
            self.logger.warning(f'No borrowers found')
            return []
        return borrowers

    async def get_fs_lending_stats(self) -> Optional[LendingStats]:
        data = await self.fs.request(URL_FS_BORROWERS)
        if data:
            return LendingStats.from_fs_json(data)

    async def fetch(self) -> Optional[LendingStats]:
        lending_stats = await self.get_fs_lending_stats()
        if not lending_stats:
            self.logger.error(f'No lending stats')
            return

        if lending_stats.data_age > MAX_AGE_TO_REPORT_ERROR:
            self.deps.emergency.report(self.name,
                                       'Lending data is too old',
                                       day=str(datetime.datetime.fromtimestamp(lending_stats.timestamp_day)))
            return

        return lending_stats
