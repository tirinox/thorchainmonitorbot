from dataclasses import dataclass
from typing import List, Optional

import ujson

from proto import NativeThorTx, thor_decode_event, DecodedEvent
from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import THOR_BLOCK_TIME
from services.lib.depcont import DepContainer
from services.lib.utils import safe_get


@dataclass
class BlockResult:
    block_no: int
    txs: List[NativeThorTx]
    tx_logs: List[dict]
    end_block_events: List[DecodedEvent]


class NativeScannerBlock(BaseFetcher):
    SLEEP_PERIOD = 5.99
    MAX_ATTEMPTS_TO_SKIP_BLOCK = 5

    def __init__(self, deps: DepContainer, sleep_period=None, last_block=0):
        sleep_period = sleep_period or THOR_BLOCK_TIME * 0.99
        super().__init__(deps, sleep_period)
        self._last_block = last_block
        self._this_block_attempts = 0

    async def _fetch_last_block(self):
        result = await self.deps.thor_connector.query_native_status_raw()
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

    def _get_is_error(self, result):
        error = result.get('error')
        if error:
            if error.get('code') != -32603:
                self.logger.error(f'Error: "{error}"!')
            return True

    async def fetch_block_results(self, block_no) -> Optional[BlockResult]:
        result = await self.deps.thor_connector.query_native_block_results_raw(block_no)
        if result is not None:
            if self._get_is_error(result):
                return

            tx_result_arr = safe_get(result, 'result', 'txs_results') or []
            decoded_txs = [self._decode_logs(tx_result) for tx_result in tx_result_arr]
            decoded_txs = [tx for tx in decoded_txs if tx]

            end_block_events = safe_get(result, 'result', 'end_block_events') or []
            decoded_end_block_events = [thor_decode_event(ev) for ev in end_block_events]

            self.logger.info(f'Block #{block_no} has {len(decoded_txs)} txs.')

            return BlockResult(block_no, [], decoded_txs, decoded_end_block_events)
        else:
            self.logger.warn(f'Error fetching block txs results #{block_no}.')

    async def fetch_block_txs(self, block_no) -> Optional[List[NativeThorTx]]:
        result = await self.deps.thor_connector.query_tendermint_block_raw(block_no)
        if result is not None:
            if self._get_is_error(result):
                return

            raw_txs = safe_get(result, 'result', 'block', 'data', 'txs') or []
            decoded_txs = [NativeThorTx.from_base64(raw) for raw in raw_txs]
            return decoded_txs
        else:
            self.logger.warn(f'Error fetching block #{block_no}.')

    def _on_error(self):
        self._this_block_attempts += 1
        if self._this_block_attempts >= self.MAX_ATTEMPTS_TO_SKIP_BLOCK:
            self.logger.error(f'Too many attempts to get block #{self._last_block}. Skipping it.')
            self._last_block += 1
            self._this_block_attempts = 0

    async def fetch(self):
        if not self._last_block:
            await self._update_last_block()

        if not self._last_block:
            self.logger.error('Still no last_block height!')
            return

        if self._last_block % 10 == 0:
            self.logger.info(f'Tick start for block #{self._last_block}.')
        else:
            self.logger.debug(f'Tick start for block #{self._last_block}.')

        while True:
            block_result = await self.fetch_one_block(self._last_block)
            if block_result is None:
                self._on_error()
                break

            # fixme: bad design?
            await self.pass_data_to_listeners(block_result)

            self._last_block += 1
            self._this_block_attempts = 0

    async def fetch_one_block(self, block_index):
        block_result = await self.fetch_block_results(block_index)
        if block_result is None:
            return

        block_result.txs = await self.fetch_block_txs(block_index)
        if block_result.txs is None:
            self.logger.error(f'Failed to get transactions of the block #{block_index}.')
            return

        return block_result
