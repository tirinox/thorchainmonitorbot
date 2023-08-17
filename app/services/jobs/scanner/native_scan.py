import asyncio
import re
from dataclasses import dataclass
from typing import List, Optional

import ujson

from proto.access import NativeThorTx, thor_decode_event, DecodedEvent
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
    is_error: bool = False

    def find_events_by_type(self, ev_type: str):
        return filter(lambda ev: ev.type == ev_type, self.end_block_events)

    TYPE_SWAP = 'swap'
    TYPE_SCHEDULED_OUT = 'scheduled_outbound'

    def find_tx_by_type(self, tx_class):
        return filter(lambda tx: isinstance(tx.first_message, tx_class), self.txs)


class NativeScannerBlock(BaseFetcher):
    MAX_ATTEMPTS_TO_SKIP_BLOCK = 5

    NAME = 'block_scanner'

    def __init__(self, deps: DepContainer, sleep_period=None, last_block=0, max_attempts=MAX_ATTEMPTS_TO_SKIP_BLOCK):
        sleep_period = sleep_period or THOR_BLOCK_TIME * 0.99
        super().__init__(deps, sleep_period)
        self._last_block = last_block
        self._this_block_attempts = 0
        self.max_attempts = max_attempts
        self.one_block_per_run = False
        self.allow_jumps = True

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
            code = error.get('code')
            if code != -32603:
                self.logger.error(f'Error: "{error}"!')
                return BlockResult(code, [], [], [], is_error=True)
            else:
                # must be that no all blocks are present, try to extract the last available block no from the error msg
                data = str(error.get('data', ''))
                match = re.findall(r'\d+', data)
                if match:
                    last_available_block = int(match[-1])
                    return BlockResult(last_available_block, [], [], [], is_error=True)

    async def fetch_block_results(self, block_no) -> Optional[BlockResult]:
        result = await self.deps.thor_connector.query_native_block_results_raw(block_no)
        if result is not None:
            if err := self._get_is_error(result):
                return err

            tx_result_arr = safe_get(result, 'result', 'txs_results') or []
            decoded_txs = [self._decode_logs(tx_result) for tx_result in tx_result_arr]
            decoded_txs = [tx for tx in decoded_txs if tx]

            end_block_events = safe_get(result, 'result', 'end_block_events') or []
            decoded_end_block_events = [thor_decode_event(ev, block_no) for ev in end_block_events]

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
            decoded_txs = [self._decode_one_tx(raw) for raw in raw_txs]
            return list(filter(bool, decoded_txs))
        else:
            self.logger.warn(f'Error fetching block #{block_no}.')
            self.deps.emergency.report(self.NAME, 'Error fetching block', block_no=block_no)

    def _decode_one_tx(self, raw):
        try:
            return NativeThorTx.from_base64(raw)
        except Exception as e:
            self.logger.error(f'Error decoding tx: {e}')

    def _on_error(self):
        self._this_block_attempts += 1
        if self._this_block_attempts >= self.max_attempts:
            self.logger.error(f'Too many attempts to get block #{self._last_block}. Skipping it.')
            self.deps.emergency.report(self.NAME, 'Block scan fail', block_no=self._last_block)

            self._last_block += 1
            self._this_block_attempts = 0

    async def ensure_last_block(self):
        while not self._last_block:
            await self._update_last_block()

            if not self._last_block:
                self.logger.error('Still no last_block height!')
                await asyncio.sleep(self.sleep_period)

    async def fetch(self):
        await self.ensure_last_block()

        if self._last_block % 10 == 0:
            self.logger.info(f'👿 Tick start for block #{self._last_block}.')
        else:
            self.logger.debug(f'👿 Tick start for block #{self._last_block}.')

        while True:
            try:
                block_result = await self.fetch_one_block(self._last_block)
                if block_result is None:
                    self._on_error()
                    break

                if block_result.is_error:
                    if self.allow_jumps and block_result.block_no > self._last_block:
                        self.logger.warning(f'It seems that no blocks available before {block_result.block_no}. '
                                            f'Jumping to it!')
                        self.deps.emergency.report(self.NAME, 'Jump block',
                                                   from_block=self._last_block,
                                                   to_block=block_result.block_no)
                        self._last_block = block_result.block_no
                        self._this_block_attempts = 0
                    else:
                        self._on_error()
                    break

            except Exception as e:
                self.logger.error(f'Error while fetching block #{self._last_block}: {e}')
                self._on_error()
                break

            await self.pass_data_to_listeners(block_result)

            self._last_block += 1
            self._this_block_attempts = 0

            if self.one_block_per_run:
                break

    async def fetch_one_block(self, block_index) -> Optional[BlockResult]:
        block_result = await self.fetch_block_results(block_index)
        if block_result is None:
            return

        if block_result.is_error:
            return block_result

        block_result.txs = await self.fetch_block_txs(block_index)
        if block_result.txs is None:
            self.logger.error(f'Failed to get transactions of the block #{block_index}.')
            return

        return block_result
