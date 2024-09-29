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

        mimir = await thor.query_mimir()
        await asyncio.sleep(self.step_sleep)

        node_mimir = await thor.query_mimir_node_accepted()
        await asyncio.sleep(self.step_sleep)

        votes = await thor.query_mimir_votes()
        await asyncio.sleep(self.step_sleep)

        votes: List[ThorMimirVote]
        node_mimir: dict

        if not constants or not mimir or node_mimir is None or votes is None:
            raise FileNotFoundError('failed to get Mimir data from THORNode')

        self.deps.mimir_const_holder.update(
            constants, mimir, node_mimir, votes,
            self.deps.node_holder.active_nodes
        )

        self.logger.info(f'Got {len(constants.constants)} CONST entries'
                         f' and {len(mimir.constants)} MIMIR entries.')
        return MimirTuple(constants, mimir, node_mimir, votes)

