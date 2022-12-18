import asyncio
from itertools import cycle
from typing import List, NamedTuple

from aiothornode.types import ThorConstants, ThorMimir, ThorMimirVote

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer


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

    async def fetch(self) -> MimirTuple:
        thor = self.deps.thor_connector
        constants, mimir, node_mimir, votes = await asyncio.gather(
            thor.query_constants(),
            thor.query_mimir(),
            thor.query_mimir_node_accepted(),
            thor.query_mimir_votes(),
        )
        votes: List[ThorMimirVote]
        node_mimir: dict

        if not constants or not mimir or node_mimir is None or votes is None:
            raise FileNotFoundError('failed to get Mimir data from THORNode')

        # # fixme: ------- 8< ---- debug ------ 8< -------
        # votes = self._dbg_randomize_votes(votes)
        # mimir, node_mimir = self._dbg_randomize_mimir(mimir, node_mimir)
        # # fixme: ------- 8< ---- debug ------ 8< -------

        self.deps.mimir_const_holder.update(
            constants, mimir, node_mimir, votes,
            self.deps.node_holder.active_nodes
        )

        self.logger.info(f'Got {len(constants.constants)} CONST entries'
                         f' and {len(mimir.constants)} MIMIR entries.')
        return MimirTuple(constants, mimir, node_mimir, votes)

    # ----- D E B U G    S T U F F -----

    def _dbg_randomize_votes(self, votes: List[ThorMimirVote]):
        # votes.append(MimirVote('LOVEME', 2, 'thor10vmz8d0qwvq5hw9susmf7nefka9usazzcvkeaj'))
        # votes.append(MimirVote('LOVEME', 2, 'thor125tlvrmxqxxldu7c7j5qeg7x90dau6fga50kh9'))
        # votes.append(MimirVote('LOVEME', 2, 'thor10697ffyya4fddsvpwj6crfwe06pxkxkmdl8kev'))
        votes.append(ThorMimirVote('ENABLESAVINGSVAULTS', 3, 'thor10f40m6nv7ulc0fvhmt07szn3n7ajd7e8xhghc3'))
        votes.append(ThorMimirVote('ENABLESAVINGSVAULTS', 2, 'thor10smhtnkaju9ng0cag5p986czp6vmqvnmnl90wh'))
        votes.append(ThorMimirVote('ENABLESAVINGSVAULTS', 2, 'thor12espg8k5fxqmclx9vyte7cducmmvrtxll40q7z'))
        return votes

    def _dbg_randomize_node_mimir_results(self, results):
        return results

    _dbg_wheel = cycle([0, 1, 0, 5825662, 0, 55555, 1])

    def _dbg_randomize_mimir(self, fresh_mimir: ThorMimir, node_mimir: dict):
        # if random.uniform(0, 1) > 0.5:
        #     fresh_mimir.constants['LOKI_CONST'] = "555"
        # if random.uniform(0, 1) > 0.3:
        #     fresh_mimir.constants['LOKI_CONST'] = "777"
        # if random.uniform(0, 1) > 0.6:
        #     fresh_mimir.constants['NativeTransactionFee'] = 300000
        # if random.uniform(0, 1) > 0.3:
        #     try:
        #         del fresh_mimir.constants['NativeTransactionFee']
        #     except KeyError:
        #         pass
        # del fresh_mimir.constants["HALTBNBTRADING"]
        # fresh_mimir.constants["HALTETHTRADING"] = 0
        # fresh_mimir.constants["HALTBNBCHAIN"] = 1233243  # 1234568
        # del fresh_mimir.constants["EMISSIONCURVE"]
        # fresh_mimir.constants['NATIVETRANSACTIONFEE'] = 4000000
        # fresh_mimir.constants['MAXLIQUIDITYRUNE'] = 10000000000000 * random.randint(1, 99)
        # fresh_mimir.constants["FULLIMPLOSSPROTECTIONBLOCKS"] = 9000
        # fresh_mimir.constants["LOVEADMIN"] = 23

        # curr = fresh_mimir.constants["SOLVENCYHALTETHCHAIN"] = next(self._dbg_wheel)
        # print(f'SOLVENCYHALTETHCHAIN = {curr}')

        return fresh_mimir, node_mimir
