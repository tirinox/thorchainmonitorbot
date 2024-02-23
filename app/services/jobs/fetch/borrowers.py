import datetime
from typing import List, Optional

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.flipside.flipside import FlipSideConnector
from services.jobs.fetch.flipside.urls import URL_FS_BORROWERS_V3
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.loans import LendingStats
from services.models.price import RuneMarketInfo


MAX_AGE_TO_REPORT_ERROR = 3 * DAY


class BorrowersFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.borrowers.fetch_period)
        super().__init__(deps, period)
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.fs = FlipSideConnector(deps.session, deps.cfg.flipside.api_key)

    async def get_borrower_list(self) -> List[str]:
        borrowers = await self.deps.midgard_connector.request(free_url_gen.url_borrowers())

        if not borrowers:
            self.logger.warning(f'No borrowers found')
            return []
        return borrowers

    async def get_real_burned_rune(self) -> float:
        market_info: RuneMarketInfo = await self.deps.rune_market_fetcher.get_rune_market_info()
        return market_info.supply_info.lending_burnt_rune

    async def get_fs_lending_stats(self) -> Optional[LendingStats]:
        data = await self.fs.request(URL_FS_BORROWERS_V3)
        if data:
            lending_stats = LendingStats.from_fs_json(data)
            if lending_stats:
                real_burned_rune = await self.get_real_burned_rune()
                if real_burned_rune is not None:
                    lending_stats = lending_stats._replace(rune_burned_rune=real_burned_rune)
            return lending_stats

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
