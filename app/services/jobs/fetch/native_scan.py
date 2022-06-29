from aiothornode.nodeclient import ThorNodePublicClient

from proto import NativeThorTx
from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import THOR_BLOCK_TIME
from services.lib.depcont import DepContainer
from services.lib.utils import safe_get


class NativeScannerBlock(BaseFetcher):
    SLEEP_PERIOD = 5.99
    CALIBRATION_PERIOD_BLOCKS = 10

    def __init__(self, deps: DepContainer, sleep_period=None):
        sleep_period = sleep_period or THOR_BLOCK_TIME * 0.99
        super().__init__(deps, sleep_period)
        self._last_block = 0
        self._thor = ThorNodePublicClient(self.deps.session, self.deps.thor_env)

    async def _fetch_last_block(self):
        result = await self._thor.request('/status?', is_rpc=True)
        if result:
            return int(safe_get(result, 'result', 'sync_info', 'latest_block_height'))

    async def _update_last_block(self):
        last_block = await self._fetch_last_block()
        if last_block:
            self._last_block = last_block
            self.logger.info(f'Updated last block number: #{self._last_block}')

    async def _fetch_block_txs(self, block_no):
        result = await self.deps.thor_connector.query_tendermint_block_raw(block_no)
        if result is not None:
            raw_txs = safe_get(result, 'result', 'block', 'data', 'txs')
            if raw_txs is not None:
                self.logger.info(f'Block #{block_no} has {len(raw_txs)} txs.')
                return [NativeThorTx.from_base64(raw) for raw in raw_txs]
        else:
            self.logger.warn(f'Error fetching block #{block_no}.')

    async def fetch(self):
        if not self._last_block:
            await self._update_last_block()

        if not self._last_block:
            return

        while True:
            if None is await self._fetch_block_txs(self._last_block):
                self.logger.info(f"No yet block: #{self._last_block}. I will try later...")
                break
            self._last_block += 1
