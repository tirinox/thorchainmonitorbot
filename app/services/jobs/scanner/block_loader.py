import logging
import re
from dataclasses import dataclass, replace
from typing import List, NamedTuple

import ujson

from proto.access import NativeThorTx, DecodedEvent, thor_decode_event
from services.lib.utils import safe_get

logger = logging.getLogger(__name__)


class LogItem(NamedTuple):
    code: int
    entries: dict
    error_message: str

    @classmethod
    def load(cls, tx_result):
        code = tx_result.get('code', 0)
        if code != 0:
            logger.warning(f'Error in tx: {tx_result.get("log")!r}; code={code}')
            entries = {}
            error_message = tx_result.get('log')
        else:
            entries = ujson.loads(tx_result.get('log'))
            error_message = ''
        return cls(
            code=code,
            entries=entries,
            error_message=error_message
        )


@dataclass
class BlockResult:
    block_no: int
    txs: List[NativeThorTx]
    tx_logs: List[LogItem]
    end_block_events: List[DecodedEvent]
    is_error: bool = False
    last_available_block: int = 0  # this is set when you requested missing block
    error_code: int = 0
    error_message: str = ''

    @property
    def is_ahead(self):
        return self.last_available_block != 0 and self.block_no > self.last_available_block

    @property
    def is_behind(self):
        return self.last_available_block != 0 and self.block_no < self.last_available_block

    def find_events_by_type(self, ev_type: str):
        return filter(lambda ev: ev.type == ev_type, self.end_block_events)

    TYPE_SWAP = 'swap'
    TYPE_SCHEDULED_OUT = 'scheduled_outbound'

    def find_tx_by_type(self, tx_class):
        return filter(lambda tx: isinstance(tx.first_message, tx_class), self.txs)

    def _validate_txs_and_logs_count(self):
        if len(self.txs) != len(self.tx_logs):
            raise ValueError(f'Block #{self.block_no}: txs and logs count mismatch'
                             f' ({len(self.txs)=} vs {len(self.tx_logs)=})')

    @property
    def only_successful(self) -> 'BlockResult':
        if not self.txs or not self.tx_logs:
            # Empty block
            return self

        self._validate_txs_and_logs_count()

        # a log is only present when tx's code == 0
        filtered_data = [(tx, log) for tx, log in zip(self.txs, self.tx_logs) if log]

        new_txs, new_logs = tuple(zip(*filtered_data))

        return replace(self, txs=new_txs, tx_logs=new_logs)

    @staticmethod
    def _get_is_error(result, requested_block_height):
        error = result.get('error')
        if error:
            code = error.get('code')
            error_message = f"{error.get('message')}/{error.get('data')}"
            if code == -32603:
                # must be that no all blocks are present, try to extract the last available block no from the error msg
                data = str(error.get('data', ''))
                match = re.findall(r'\d+', data)
                if match:
                    last_available_block = int(match[-1])
                    return BlockResult(requested_block_height, [], [], [],
                                       is_error=True, error_code=code, error_message=error_message,
                                       last_available_block=last_available_block)

            # else general error
            return BlockResult(requested_block_height, [], [], [],
                               is_error=True, error_code=code, error_message=error_message)

    @staticmethod
    def _decode_one_tx(raw):
        try:
            return NativeThorTx.from_base64(raw)
        except Exception as e:
            logger.error(f'Error decoding tx: {e}')

    @classmethod
    def load_txs(cls, result, block_no):
        if cls._get_is_error(result, block_no):
            return

        raw_txs = safe_get(result, 'result', 'block', 'data', 'txs') or []
        # some of them can be None!
        return [cls._decode_one_tx(raw) for raw in raw_txs]

    @classmethod
    def load_block(cls, block_results_raw, block_no):
        if err := cls._get_is_error(block_results_raw, block_no):
            return err

        tx_result_arr = safe_get(block_results_raw, 'result', 'txs_results') or []

        decoded_tx_logs = [LogItem.load(tx_result) for tx_result in tx_result_arr]

        end_block_events = safe_get(block_results_raw, 'result', 'end_block_events') or []
        decoded_end_block_events = [thor_decode_event(ev, block_no) for ev in end_block_events]

        # txs are empty so far; use load_txs to fill them
        return BlockResult(block_no, [], decoded_tx_logs, decoded_end_block_events)

    def fill_transactions(self, txs):
        self.txs = txs
        self._validate_txs_and_logs_count()

        # fill tx codes from logs
        for tx, log in zip(self.txs, self.tx_logs):
            if tx and log:
                tx.code = log.code

        return self
