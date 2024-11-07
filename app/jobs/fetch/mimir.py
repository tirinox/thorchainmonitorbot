import asyncio
from typing import List, NamedTuple

from api.aionode.types import ThorConstants, ThorMimir, ThorMimirVote
from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer


class MimirTuple(NamedTuple):
    constants: ThorConstants
    mimir: ThorMimir
    node_mimir: dict
    votes: List[ThorMimirVote]


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
            raise FileNotFoundError('failed to get Constants data from THORNode')

        mimir = await thor.query_mimir()
        await asyncio.sleep(self.step_sleep)

        if not mimir or not mimir.constants:
            raise FileNotFoundError('failed to get Mimir data from THORNode')

        node_mimir = await thor.query_mimir_node_accepted()
        await asyncio.sleep(self.step_sleep)

        if node_mimir is None:
            raise FileNotFoundError('failed to get Node Mimir data from THOR')

        votes = await thor.query_mimir_votes()
        await asyncio.sleep(self.step_sleep)

        if votes is None:
            raise FileNotFoundError('failed to get Mimir Votes data from THOR')

        votes: List[ThorMimirVote]
        node_mimir: dict

        self.deps.mimir_const_holder.update(
            constants, mimir, node_mimir, votes,
            self.deps.node_holder.active_nodes
        )

        self.logger.info(f'Got {len(constants.constants)} CONST entries'
                         f' and {len(mimir.constants)} MIMIR entries.')
        return MimirTuple(constants, mimir, node_mimir, votes)

