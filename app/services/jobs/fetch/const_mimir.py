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

    async def fetch(self) -> Tuple[ThorConstants, ThorMimir]:
        last_constants, last_mimir = await asyncio.gather(
            self.fetch_constants_fallback(),
            self.fetch_mimir_fallback(),
        )

        # last_constants, last_mimir = await asyncio.gather(
        #     self.deps.thor_connector.query_constants(),
        #     self.deps.thor_connector.query_mimir(),
        # )

        self.deps.mimir_const_holder.update(last_constants, last_mimir)

        self.logger.info(f'Got {len(last_constants.constants)} CONST entries'
                         f' and {len(last_mimir.constants)} MIMIR entries.')
        return last_constants, last_mimir
