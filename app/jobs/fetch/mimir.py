from jobs.fetch.base import BaseFetcher
from jobs.runeyield.date2block import DateToBlockMapper
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from models.mimir import MimirTuple


class ConstMimirFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.constants.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> MimirTuple:
        return await self.deps.mimir_cache.get()


class MimirFetcherHistory(BaseFetcher):
    def __init__(self, deps: DepContainer, start_height, step=10, sleep_period=0.1):
        super().__init__(deps, sleep_period=sleep_period)
        self.current_height = start_height
        self.step = step
        self.block_mapper = DateToBlockMapper(deps)

    async def fetch(self) -> MimirTuple:
        data = await self.deps.mimir_cache.get_for_height_no_cache(self.current_height)

        # we must set timestamp for historical data, otherwise it will be 0 and cause issues
        block_date = await self.block_mapper.get_datetime_by_block_height(self.current_height)
        data.ts = block_date.timestamp() if block_date else 0

        self.current_height += self.step
        return data
