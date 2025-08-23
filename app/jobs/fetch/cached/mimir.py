import asyncio

from api.aionode.connector import ThorConnector
from jobs.fetch.cached.base import CachedDataSource
from jobs.fetch.cached.last_block import LastBlockCached
from lib.date_utils import MINUTE
from models.mimir import MimirTuple


class MimirCached(CachedDataSource[MimirTuple]):
    ATTEMPTS = 5

    def __init__(self, thor_connector: ThorConnector, last_block_cache: LastBlockCached):
        # todo: make it configurable in the future
        super().__init__(cache_period=MINUTE, retry_times=self.ATTEMPTS)
        self.step_sleep = 0.5
        self.thor_connector = thor_connector
        self.last_block_cache = last_block_cache

    async def _load(self) -> MimirTuple:
        thor = self.thor_connector

        # step by step
        constants = await thor.query_constants()
        if not constants or not constants.constants:
            raise FileNotFoundError('Failed to get Constants data from THORNode')

        await asyncio.sleep(self.step_sleep)

        mimir = await thor.query_mimir()
        if not mimir or not mimir.constants:
            raise FileNotFoundError('Failed to get Mimir data from THORNode')

        await asyncio.sleep(self.step_sleep)

        accepted_node_mimir = await thor.query_mimir_node_accepted()
        if accepted_node_mimir is None:
            raise FileNotFoundError('Failed to get Node Mimir data from THOR')

        await asyncio.sleep(self.step_sleep)

        votes = await thor.query_mimir_votes()
        await asyncio.sleep(self.step_sleep)

        if votes is None:
            raise FileNotFoundError('Failed to get Mimir Votes data from THOR')

        last_block = await self.last_block_cache.get_thor_block()

        return MimirTuple(
            constants, mimir, accepted_node_mimir, votes,
            last_thor_block=last_block,
        )
