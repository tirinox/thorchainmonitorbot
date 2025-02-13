from contextlib import suppress

from aiohttp import ClientSession

from lib.constants import thor_to_float, NATIVE_RUNE_SYMBOL
from lib.logs import WithLogger

MAYA_POOLS_URL = 'https://mayanode.mayachain.info/mayachain/pools'


class MayaConnector(WithLogger):
    def __init__(self, session: ClientSession):
        super().__init__()
        self.session = session

    async def get_maya_pool_rune(self):
        with suppress(Exception):
            self.logger.info(f'Fetching Maya pool balance from {MAYA_POOLS_URL}')
            async with self.session.get(MAYA_POOLS_URL) as resp:
                j = await resp.json()
                rune_pool = next(p for p in j if p['asset'] == NATIVE_RUNE_SYMBOL)
                return thor_to_float(rune_pool['balance_asset'])
        return 0.0
