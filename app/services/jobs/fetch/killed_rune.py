from typing import List

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.killed_rune import KilledRuneEntry

DEFAULT_API_URL = 'https://node-api.flipsidecrypto.com/api/v2/queries/b5f325f6-8a42-47eb-9faf-ba8b0bdf1438/data/latest'


class KilledRuneFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.killed_rune.fetch_period)
        self.url = deps.cfg.as_str('killed_rune.api_url', DEFAULT_API_URL)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> List[KilledRuneEntry]:
        async with self.deps.session.get(self.url) as resp:
            data = await resp.json()
            return [KilledRuneEntry.from_flipside_json(item) for item in data]
