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
        self.last_constants: ThorConstants = ThorConstants()
        self.last_mimir: ThorMimir = ThorMimir()

    MIMIR_PREFIX = 'mimir//'

    @staticmethod
    def get_constant_static(name: str, mimir: ThorMimir, constants: ThorConstants, default=0, const_type=int):
        raw_hardcoded_value = constants.constants.get(name, 0)
        hardcoded_value = const_type(raw_hardcoded_value) if const_type else raw_hardcoded_value

        prefix = ConstMimirFetcher.MIMIR_PREFIX
        mimir_name = f'{prefix}{name.upper()}'

        if mimir_name in mimir.constants:
            v = mimir.constants.get(mimir_name, default)
            return const_type(v) if const_type is not None else v
        else:
            return hardcoded_value

    @staticmethod
    def get_hardcoded_const_static(name: str, const_holder: ThorConstants, default=None):
        prefix = ConstMimirFetcher.MIMIR_PREFIX
        if name.startswith(prefix):
            pure_name = name[len(prefix):]
            for k, v in const_holder.constants.items():
                if pure_name.upper() == k.upper():
                    return v
            return default
        else:
            return const_holder.constants.get(name)

    def get_constant(self, name: str, default=0, const_type=int):
        return self.get_constant_static(name, self.last_mimir, self.last_constants, default=default,
                                        const_type=const_type)

    def get_hardcoded_const(self, name: str, default=None):
        return self.get_hardcoded_const_static(name, self.last_constants, default)

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
        self.last_constants, self.last_mimir = await asyncio.gather(
            self.fetch_constants_fallback(),
            self.fetch_mimir_fallback(),
        )
        # self.last_constants, self.last_mimir = await asyncio.gather(
        #     self.deps.thor_connector.query_constants(),
        #     self.deps.thor_connector.query_mimir(),
        # )
        self.logger.info(f'Got {len(self.last_constants.constants)} CONST entries'
                         f' and {len(self.last_mimir.constants)} MIMIR entries.')
        return self.last_constants, self.last_mimir
