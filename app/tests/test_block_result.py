from datetime import datetime
from pathlib import Path

from jobs.scanner.block_result import BlockResult
from lib.utils import load_json

BLOCK_NO = 0
TARGET_TX_ID = '44546C04AB742EC86F3380C7647CEC6D0496CF6F20E00BDD8E17E50CB23A84A8'
SAMPLE_BLOCK_PATH = Path(__file__).with_name('sample_data') / 'block-limit-quorum.json'


def test_quorum_observed_tx_is_recognized_as_inbound():
    block = BlockResult.load_block(load_json(SAMPLE_BLOCK_PATH), BLOCK_NO)

    observed_txs_by_id = {tx.tx_id: tx for tx in block.all_observed_txs}
    target_tx = observed_txs_by_id[TARGET_TX_ID]

    assert target_tx.tx_id == TARGET_TX_ID
    assert target_tx.chain == 'XRP'
    assert target_tx.is_inbound is True
    assert target_tx.is_outbound is False
    assert target_tx.status == 'incomplete'
    assert target_tx.original['__is_quorum'] is True


def test_quorum_block_header_time_with_nanoseconds_is_parsed():
    block = BlockResult.load_block(load_json(SAMPLE_BLOCK_PATH), BLOCK_NO)

    expected_ts = datetime(2026, 3, 26, 21, 36, 57, 934136).timestamp()
    assert block.timestamp == expected_ts


def test_block_header_time_with_millisecond_precision_is_parsed():
    raw_block = {
        'header': {
            'time': '2026-04-03T18:58:33.308Z',
        },
        'txs': [],
        'begin_block_events': [],
        'end_block_events': [],
    }

    block = BlockResult.load_block(raw_block, 25615925)

    assert block.block_no == 25615925
    assert block.timestamp == datetime(2026, 4, 3, 18, 58, 33, 308000).timestamp()
