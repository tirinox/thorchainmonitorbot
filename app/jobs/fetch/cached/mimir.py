import asyncio

from api.aionode.connector import ThorConnector
from jobs.fetch.cached.base import CachedDataSource
from jobs.fetch.cached.last_block import LastBlockCached
from lib.date_utils import MINUTE, now_ts
from models.mimir import MimirTuple, MimirHolder
from models.mimir_naming import MimirNameRules, MIMIR_DICT_FILENAME


class MimirCached(CachedDataSource[MimirTuple]):
    ATTEMPTS = 5

    def __init__(self, thor_connector: ThorConnector, last_block_cache: LastBlockCached):
        # todo: make it configurable in the future
        super().__init__(cache_period=MINUTE, retry_times=self.ATTEMPTS)
        self.step_sleep = 0.2
        self.thor_connector = thor_connector
        self.last_block_cache = last_block_cache
        self.rules = MimirNameRules()
        self.rules.load(MIMIR_DICT_FILENAME)

    async def _load(self, height=None) -> MimirTuple:
        thor = self.thor_connector

        # step by step
        constants = await thor.query_constants(height)
        if not constants or not constants.constants:
            raise FileNotFoundError('Failed to get Constants data from THORNode')

        await asyncio.sleep(self.step_sleep)

        mimir = await thor.query_mimir(height)
        if not mimir or not mimir.constants:
            raise FileNotFoundError('Failed to get Mimir data from THORNode')

        await asyncio.sleep(self.step_sleep)

        accepted_node_mimir = await thor.query_mimir_node_accepted(height)
        if accepted_node_mimir is None:
            raise FileNotFoundError('Failed to get Node Mimir data from THOR')

        await asyncio.sleep(self.step_sleep)

        votes = await thor.query_mimir_votes(height)
        await asyncio.sleep(self.step_sleep)

        if votes is None:
            raise FileNotFoundError('Failed to get Mimir Votes data from THOR')

        last_block = height or await self.last_block_cache.get_thor_block()

        return MimirTuple(
            constants, mimir, accepted_node_mimir, votes,
            thor_height=last_block,
            ts=(now_ts() if height is None else 0)
        )

    async def get_for_height_no_cache(self, height) -> MimirTuple:
        return await self._load(height=height)

    async def get_mimir_holder(self, height=None) -> MimirHolder:
        if height:
            mimir_tuple = await self.get_for_height_no_cache(height)
        else:
            mimir_tuple = await self.get()
        holder = MimirHolder()
        holder.mimir_rules = self.rules
        return holder.update(mimir_tuple, [], with_voting=False)
