import typing

import ujson
from aiothornode.nodeclient import ThorNodePublicClient

from proto import NativeThorTx
from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import THOR_BLOCK_TIME
from services.lib.depcont import DepContainer
from services.lib.utils import safe_get


class BlockResult(typing.NamedTuple):
    block_no: int
    txs: typing.List[NativeThorTx]
    tx_logs: typing.List[dict]


class NativeScannerBlock(BaseFetcher):
    SLEEP_PERIOD = 5.99

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

    @staticmethod
    def _decode_logs(tx_result):
        code = tx_result.get('code', 0)
        if code != 0:
            return
        return ujson.loads(tx_result.get('log'))

    async def fetch_block_results(self, block_no):
        result = await self._thor.request(f'/block_results?height={block_no}', is_rpc=True)
        if result is not None:
            # end_block_events
            tx_result_arr = safe_get(result, 'result', 'txs_results')
            if tx_result_arr is not None:
                decoded_txs = [self._decode_logs(tx_result) for tx_result in tx_result_arr]
                decoded_txs = [tx for tx in decoded_txs if tx]
                self.logger.info(f'Block #{block_no} has {len(decoded_txs)} txs.')
                return decoded_txs
        else:
            self.logger.warn(f'Error fetching block txs results #{block_no}.')

    async def fetch_block_txs(self, block_no):
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
            tx_logs = await self.fetch_block_results(self._last_block)
            if tx_logs is None:
                self.logger.debug(f"No yet block: #{self._last_block}. I will try later...")
                break

            txs = await self.fetch_block_txs(self._last_block)
            await self.pass_data_to_listeners(BlockResult(self._last_block, txs, tx_logs))
            self._last_block += 1
