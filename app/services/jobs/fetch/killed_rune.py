from typing import List

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger, WithLogger
from services.models.killed_rune import KilledRuneEntry

DEFAULT_API_URL = 'https://node-api.flipsidecrypto.com/api/v2/queries/b5f325f6-8a42-47eb-9faf-ba8b0bdf1438/data/latest'


class KilledRuneFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.killed_rune.fetch_period)
        self.url = deps.cfg.as_str('killed_rune.api_url', DEFAULT_API_URL)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> List[KilledRuneEntry]:
        async with self.deps.session.get(self.url) as resp:
            data = await resp.json()
            self.logger.info(f'Total: {len(data)} objects')
            return [KilledRuneEntry.from_flipside_json(item) for item in data]


class KilledRuneStore(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

    async def on_data(self, sender, data: List[KilledRuneEntry]):
        latest_one = data[0]
        if latest_one.block_id > 0:
            self.deps.killed_rune = latest_one
            self.logger.info(f'Updated last killed rune: {latest_one}')
