import asyncio
from typing import Tuple

from aiothornode.types import ThorConstants, ThorMimir

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id


class ConstMimirFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.constants.fetch_period)
        super().__init__(deps, sleep_period)
        self.url_gen = get_url_gen_by_network_id(deps.cfg.network_id)
        self.last_constants: ThorConstants = ThorConstants()
        self.last_mimir: ThorMimir = ThorMimir()

    @staticmethod
    def get_constant_static(name: str, mimir: ThorMimir, constants: ThorConstants, default=0, const_type=int):
        hardcoded_value = const_type(constants.constants.get(name, 0))

        wanted_const = f'mimir//{name.upper()}'
        if wanted_const in mimir.constants:
            return const_type(mimir.constants.get(wanted_const, default))
        else:
            return hardcoded_value

    def get_constant(self, name: str, default=0, const_type=int):
        return self.get_constant_static(name, self.last_mimir, self.last_constants, default=default,
                                        const_type=const_type)

    async def fetch(self) -> Tuple[ThorConstants, ThorMimir]:
        self.last_constants, self.last_mimir = await asyncio.gather(
            self.deps.thor_connector.query_constants(),
            self.deps.thor_connector.query_mimir(),
        )
        self.logger.info(f'Got {len(self.last_constants.constants)} CONST entries'
                         f' and {len(self.last_mimir.constants)} MIMIR entries.')
        return self.last_constants, self.last_mimir
