import asyncio
from typing import Tuple

from aiothornode.nodeclient import ThorNodePublicClient
from aiothornode.types import ThorConstants, ThorMimir

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer


class ConstMimirFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.constants.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch_constants_midgard(self) -> ThorConstants:
        data = await self.deps.midgard_connector.request_random_midgard('/thorchain/constants')
        return ThorConstants.from_json(data)

    async def fetch_constants_fallback(self) -> ThorConstants:
        client = ThorNodePublicClient(self.deps.session)
        for attempt in range(1, 5):
            response = await client.request('/thorchain/constants')
            if response is not None:
                return ThorConstants.from_json(response)
            else:
                self.logger.warning(f'fail attempt: #{attempt}')
        return ThorConstants()

    async def fetch_mimir_fallback(self) -> ThorMimir:
        client = ThorNodePublicClient(self.deps.session)
        for attempt in range(1, 5):
            response = await client.request('/thorchain/mimir')
            if response is not None:
                return ThorMimir.from_json(response)
            else:
                self.logger.warning(f'fail attempt: #{attempt}')
        return ThorMimir()

    def _dbg_randomize_mimir(self, fresh_mimir: ThorMimir):
        # if random.uniform(0, 1) > 0.5:
        #     fresh_mimir.constants['mimir//LOKI_CONST'] = "555"
        # if random.uniform(0, 1) > 0.3:
        #     fresh_mimir.constants['mimir//LOKI_CONST'] = "777"
        # if random.uniform(0, 1) > 0.6:
        #     fresh_mimir.constants['mimir//NativeTransactionFee'] = 300000
        # if random.uniform(0, 1) > 0.3:
        #     try:
        #         del fresh_mimir.constants['mimir//NativeTransactionFee']
        #     except KeyError:
        #         pass
        # del fresh_mimir.constants["mimir//HALTBNBTRADING"]
        # fresh_mimir.constants["mimir//HALTETHTRADING"] = 1234568
        # fresh_mimir.constants["mimir//HALTBNBCHAIN"] = 1233243  # 1234568
        # del fresh_mimir.constants["mimir//EMISSIONCURVE"]
        # fresh_mimir.constants['mimir//NATIVETRANSACTIONFEE'] = 4000000
        # fresh_mimir.constants['mimir//MAXLIQUIDITYRUNE'] = 10000000000000 * random.randint(1, 99)
        # fresh_mimir.constants["mimir//FULLIMPLOSSPROTECTIONBLOCKS"] = 10000 * random.randint(1, 999)
        return fresh_mimir

    async def fetch(self) -> Tuple[ThorConstants, ThorMimir]:
        last_constants, last_mimir = await asyncio.gather(
            self.fetch_constants_fallback(),
            self.fetch_mimir_fallback(),
        )

        # last_mimir = self._dbg_randomize_mimir(last_mimir)  # fixme

        # last_constants, last_mimir = await asyncio.gather(
        #     self.deps.thor_connector.query_constants(),
        #     self.deps.thor_connector.query_mimir(),
        # )

        self.deps.mimir_const_holder.update(last_constants, last_mimir)

        self.logger.info(f'Got {len(last_constants.constants)} CONST entries'
                         f' and {len(last_mimir.constants)} MIMIR entries.')
        return last_constants, last_mimir
