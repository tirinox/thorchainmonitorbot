import logging
import re
from dataclasses import dataclass, replace
from typing import List, NamedTuple, Iterable

from jobs.scanner.tx import NativeThorTx, ThorEvent, ThorObservedTx
from lib.date_utils import date_parse_rfc
from lib.utils import safe_get

logger = logging.getLogger(__name__)


class ScannerError(NamedTuple):
    code: int
    message: str
    last_available_block: int = 0

    CODE_FUTURE = 2
    CODE_ANCIENT = 3


def is_block_error(result):
    code = result.get('code')
    message = result.get('message')
    if code and message:
        last_available_block = 0
        if code == ScannerError.CODE_ANCIENT:  # too old
            match = re.findall(r'\d+', message)
            if match:
                last_available_block = int(match[-1])
        return ScannerError(code, message, last_available_block)


@dataclass
class BlockResult:
    block_no: int
    txs: List[NativeThorTx]
    end_block_events: List[ThorEvent]
    begin_block_events: List[ThorEvent]
    error: ScannerError
    timestamp: int = 0

    @property
    def is_error(self):
        return self.error.code != 0

    @property
    def is_ahead(self):
        return self.error and self.error.code == self.error.CODE_FUTURE

    @property
    def is_behind(self):
        return self.error.last_available_block != 0 and self.block_no < self.error.last_available_block

    def find_tx_by_type(self, msg_type) -> Iterable[NativeThorTx]:
        for tx in self.txs:
            for message in tx.messages:
                if message.type == msg_type:
                    yield tx

    @property
    def only_successful(self) -> 'BlockResult':
        if not self.txs:
            # Empty block
            return self

        filtered_txs = [tx for tx in self.txs if tx.is_success]
        return replace(self, txs=filtered_txs)

    @classmethod
    def load_block(cls, block_results_raw: dict, block_no):
        if err := is_block_error(block_results_raw):
            return BlockResult(block_no, txs=[], end_block_events=[], begin_block_events=[], error=err, timestamp=0)

        txs = [NativeThorTx.from_dict(tx, block_no) for tx in block_results_raw.get('txs', [])]
        begin_block_events = [ThorEvent.from_dict(e, block_no) for e in block_results_raw.get('begin_block_events', [])]
        end_block_events = [ThorEvent.from_dict(e, block_no) for e in block_results_raw.get('end_block_events', [])]

        ts = date_parse_rfc(safe_get(block_results_raw, 'header', 'time')).timestamp()

        return cls(
            block_no=block_no,
            txs=txs,
            end_block_events=end_block_events,
            begin_block_events=begin_block_events,
            error=ScannerError(0, ''),
            timestamp=ts,
        )

    @property
    def all_event_types(self):
        return set(ev.type for ev in self.end_block_events)

    @property
    def all_observed_tx_in(self) -> List[ThorObservedTx]:
        observed_txs = {}
        for tx in self.txs:
            for message in tx.messages:
                if message.type == message.MsgObservedTxIn:
                    for inner_tx in message.txs:
                        observed_txs[inner_tx['id']] = inner_tx
        return [
            ThorObservedTx.from_dict(d) for d in observed_txs.values()
        ]
