from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer


class AccountNumberFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.wallet_counter.fetch_period)
        super().__init__(deps, sleep_period)

    URL_PATH = '/cosmos/auth/v1beta1/accounts?pagination.limit=1&pagination.count_total=true'

    async def fetch(self) -> int:
        data = await self.deps.thor_connector.query_raw(self.URL_PATH)
        n = int(data['pagination']['total'])
        self.logger.info(f"Number of Rune wallets is {n}")
        return n
