from aiothornode.nodeclient import ThorNodePublicClient

from proto import NativeThorTx
from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import THOR_BLOCK_TIME
from services.lib.depcont import DepContainer
from services.lib.utils import safe_get


class NativeScannerBlock(BaseFetcher):
    SLEEP_PERIOD = 5.99
    CALIBRATION_PERIOD_BLOCKS = 10

    def __init__(self, deps: DepContainer, sleep_pediod=None):
        sleep_pediod = sleep_pediod or THOR_BLOCK_TIME * 0.99
        super().__init__(deps, sleep_pediod)
        self._last_block = 0
        self._thor = ThorNodePublicClient(self.deps.session, self.deps.thor_env)
        self._tick = 0

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
        if result:
            raw_txs = safe_get(result, 'result', 'block', 'data', 'txs')
            self.logger.info(f'Block #{block_no} has {len(raw_txs)} txs.')
            return [NativeThorTx.from_base64(raw) for raw in raw_txs]
        else:
            self.logger.warn(f'Error fetching block #{block_no}.')

    async def _calibrate(self):
        self.logger.info('Calibration start.')
        last_block = await self._fetch_last_block()

        if not last_block:
            self.logger.error('Failed to calibrate, no last block!')
            return

        while last_block - self._last_block > 0:
            self.logger.info(f'Lag is {last_block - self._last_block} blocks '
                             f'({last_block = } and our block {self._last_block}).')
            await self._get_and_handle_next_block()

    async def _get_and_handle_next_block(self):
        txs = await self._fetch_block_txs(self._last_block)
        if txs is not None:
            self._last_block += 1
            if txs:
                await self.pass_data_to_listeners(txs)
        else:
            self.logger.warning(f'Yet no block: #{self._last_block}. I will try on the next tick...')

    async def fetch(self):
        if not self._last_block:
            await self._update_last_block()

        if not self._last_block:
            return

        self._tick += 1

        if self._tick % self.CALIBRATION_PERIOD_BLOCKS == 0:
            await self._calibrate()
        else:
            await self._get_and_handle_next_block()

