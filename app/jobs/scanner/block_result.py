import logging
import re
from dataclasses import dataclass, replace
from typing import List, NamedTuple

from jobs.scanner.tx import NativeThorTx, ThorEvent

logger = logging.getLogger(__name__)


class ScannerError(NamedTuple):
    code: int
    message: str
    last_available_block: int = 0


def is_block_error(result):
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
                return ScannerError(code, error_message, last_available_block)

        # else general error
        return ScannerError(code, error_message)


@dataclass
class BlockResult:
    block_no: int
    txs: List[NativeThorTx]
    end_block_events: List[ThorEvent]
    begin_block_events: List[ThorEvent]
    error: ScannerError

    @property
    def is_error(self):
        return self.error.code != 0

    @property
    def is_ahead(self):
        return self.error.last_available_block != 0 and self.block_no > self.error.last_available_block

    @property
    def is_behind(self):
        return self.error.last_available_block != 0 and self.block_no < self.error.last_available_block

    def find_tx_by_type(self, tx_class):
        return filter(lambda tx: isinstance(tx.first_message, tx_class), self.txs)

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
            return BlockResult(block_no, txs=[], end_block_events=[], begin_block_events=[], error=err)

        txs = [NativeThorTx.from_dict(tx) for tx in block_results_raw.get('txs', [])]
        begin_block_events = [ThorEvent.from_dict(e) for e in block_results_raw.get('begin_block_events', [])]
        end_block_events = [ThorEvent.from_dict(e) for e in block_results_raw.get('end_block_events', [])]

        return cls(
            block_no,
            txs=txs,
            end_block_events=end_block_events,
            begin_block_events=begin_block_events,
            error=ScannerError(0, '')
        )

    @property
    def all_event_types(self):
        return set(ev.type for ev in self.end_block_events)
