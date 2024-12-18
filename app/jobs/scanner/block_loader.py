import logging
import re
from dataclasses import dataclass, replace
from typing import List, NamedTuple

import ujson

from lib.utils import safe_get
from proto.access import NativeThorTx, DecodedEvent, thor_decode_event

logger = logging.getLogger(__name__)


class LogItem(NamedTuple):
    code: int
    events: list
    error_message: str

    @classmethod
    def load(cls, tx_result):
        code = tx_result.get('code', 0)
        if code != 0:
            events = []
            error_message = tx_result.get('log')
        else:
            # entries = ujson.loads(tx_result.get('log'))
            # v3
            entries = tx_result.get('events', [])
            events = [DecodedEvent.from_dict(raw_event) for raw_event in entries]
            error_message = ''
        return cls(
            code=code,
            events=events,
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

    TYPE_SWAP = 'swap'
    TYPE_SCHEDULED_OUT = 'scheduled_outbound'

    def find_tx_by_type(self, tx_class):
        return filter(lambda tx: isinstance(tx.first_message, tx_class), self.txs)

    def _validate_txs_and_logs_count(self):
        if self.txs is None:
            raise ValueError(f'Block #{self.block_no}: txs is None')

        if self.tx_logs is None:
            raise ValueError(f'Block #{self.block_no}: tx_logs is None')

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
        filtered_data = [(tx, log) for tx, log in zip(self.txs, self.tx_logs) if log and log.code == 0]

        new_txs, new_logs = tuple(zip(*filtered_data)) if filtered_data else ([], [])

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

        for log in decoded_tx_logs:
            if log.code != 0:
                logger.error(f'Error in tx: code={log.code}; error_message={log.error_message}; block #{block_no}')

        end_block_events = safe_get(block_results_raw, 'result', 'finalize_block_events') or []
        decoded_end_block_events = [thor_decode_event(ev, block_no) for ev in end_block_events]

        # txs are empty so far; use load_txs to fill them
        return BlockResult(block_no, txs=[], tx_logs=decoded_tx_logs, end_block_events=decoded_end_block_events)

    def fill_transactions(self, txs: List[NativeThorTx]):
        self.txs = txs
        self._validate_txs_and_logs_count()

        # fill tx codes from logs
        for tx, log in zip(self.txs, self.tx_logs):
            if tx and log:
                tx.code = log.code

        return self

    @property
    def all_event_types(self):
        return set(ev.type for ev in self.end_block_events)

    def find_logs_by_type(self, ev_type: str):
        for log in self.tx_logs:
            for event in log.events:
                if event.type == ev_type:
                    yield event
