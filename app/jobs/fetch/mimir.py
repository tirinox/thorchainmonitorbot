import asyncio

from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from models.mimir import MimirTuple


class ConstMimirFetcher(BaseFetcher):
    ATTEMPTS = 5

    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.constants.fetch_period)
        super().__init__(deps, sleep_period)
        self.step_sleep = deps.cfg.sleep_step

    async def fetch(self) -> MimirTuple:
        thor = self.deps.thor_connector

        # step by step
        constants = await thor.query_constants()
        await asyncio.sleep(self.step_sleep)

        if not constants or not constants.constants:
            raise FileNotFoundError('Failed to get Constants data from THORNode')

        mimir = await thor.query_mimir()
        await asyncio.sleep(self.step_sleep)

        if not mimir or not mimir.constants:
            raise FileNotFoundError('Failed to get Mimir data from THORNode')

        node_mimir = await thor.query_mimir_node_accepted()
        await asyncio.sleep(self.step_sleep)

        if node_mimir is None:
            raise FileNotFoundError('Failed to get Node Mimir data from THOR')

        votes = await thor.query_mimir_votes()
        await asyncio.sleep(self.step_sleep)

        if votes is None:
            raise FileNotFoundError('Failed to get Mimir Votes data from THOR')

        return MimirTuple(
            constants, mimir, node_mimir, votes,
            active_nodes=self.deps.node_holder.active_nodes,
            last_thor_block=int(self.deps.last_block_store),
        )
