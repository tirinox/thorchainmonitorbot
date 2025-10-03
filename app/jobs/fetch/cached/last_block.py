from datetime import datetime
from typing import Dict, NamedTuple

from api.aionode.connector import ThorConnector
from api.aionode.types import ThorLastBlock
from jobs.fetch.cached.base import CachedDataSource
from lib.constants import THOR_BLOCK_TIME
from lib.delegates import WithDelegates, INotified

BlockDict = Dict[str, ThorLastBlock]


class EventLastBlock(NamedTuple):
    thor_block: int
    block_dict: BlockDict


class LastBlockCached(CachedDataSource[BlockDict]):
    """
    THORNode last block cache.
    """

    def __init__(self, thor_connector: ThorConnector, cache_period=THOR_BLOCK_TIME):
        super().__init__(cache_period, retry_times=2, retry_exponential_growth_factor=1.5)
        self.thor_connector = thor_connector

    async def _load(self) -> BlockDict:
        data = await self.thor_connector.query_last_blocks()
        if not data:
            raise RuntimeError('Failed to fetch swap history data')
        block_dict = {last_block.chain: last_block for last_block in data}
        return block_dict

    async def get_thor_block(self):
        data = await self.get()
        # first key from dict
        if not data:
            return None

        first_key = next(iter(data))
        return data[first_key].thorchain

    @staticmethod
    def calc_block_time_ago(seconds, last_block):
        if last_block:
            return int(last_block - seconds / THOR_BLOCK_TIME)

    async def get_thor_block_time_ago(self, seconds):
        last_block = await self.get_thor_block()
        return self.calc_block_time_ago(seconds, last_block)

    async def get_timestamp_of_block(self, block_height: int) -> int:
        last_block = await self.get_thor_block()
        current_timestamp = datetime.now().timestamp()
        delta_block = last_block - block_height
        estimated_timestamp = current_timestamp - (delta_block * THOR_BLOCK_TIME)
        return int(estimated_timestamp)


class LastBlockEventGenerator(WithDelegates, INotified):
    """
    Generates an event with the last THORNode block.
    """

    def __init__(self, last_block_cached: LastBlockCached):
        super().__init__()
        self.last_block_cached = last_block_cached

    async def on_data(self, sender, data):
        block_dict = await self.last_block_cached.get()
        if not block_dict:
            return None
        last_block = next(iter(block_dict.values())).thorchain
        ev = EventLastBlock(thor_block=last_block, block_dict=block_dict)
        await self.pass_data_to_listeners(sender, ev)
