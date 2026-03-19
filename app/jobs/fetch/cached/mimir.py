import asyncio

from api.aionode.connector import ThorConnector
from api.aionode.types import ThorConstants, ThorMimir
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

    async def _load(self, height=None, only_votes=False) -> MimirTuple:
        thor = self.thor_connector

        if only_votes:
            constants = ThorConstants()
            mimir = ThorMimir()
            accepted_node_mimir = {}
        else:
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
        if height is None:
            ts = now_ts()
        else:
            ts = 0

        return MimirTuple(
            constants, mimir, accepted_node_mimir, votes,
            thor_height=last_block,
            ts=ts
        )

    async def get_for_height_no_cache(self, height, only_votes=False) -> MimirTuple:
        return await self._load(height=height, only_votes=only_votes)

    async def get_mimir_holder(self) -> MimirHolder:
        mimir_tuple = await self.get()
        holder = MimirHolder()
        holder.mimir_rules = self.rules
        holder.update(mimir_tuple, [])
        holder.last_thor_block = mimir_tuple.thor_height
        holder.last_timestamp = mimir_tuple.ts
        return holder
