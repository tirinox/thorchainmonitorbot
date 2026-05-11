from datetime import datetime
from pathlib import Path

from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.tx import NativeThorTx, ThorMessageType, ThorTxMessage
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


def _make_quorum_tx(native_hash: str, observed_tx_id: str, *, memo: str, from_address: str) -> NativeThorTx:
    return NativeThorTx(
        tx_hash=native_hash,
        code=0,
        events=[],
        height=BLOCK_NO,
        original={},
        signers=[],
        messages=[ThorTxMessage.from_dict({
            '@type': ThorMessageType.MsgObservedTxQuorum.value,
            'quoTx': {
                'obsTx': {
                    'tx': {
                        'id': observed_tx_id,
                        'chain': 'BTC',
                        'from_address': from_address,
                        'to_address': 'thor1vault',
                        'coins': [],
                        'gas': [],
                        'memo': memo,
                    },
                    'status': 'incomplete',
                    'out_hashes': [],
                    'block_height': '123',
                    'finalise_height': '123',
                },
                'inbound': True,
            },
        })],
        memo='',
        timestamp=0,
    )


def test_all_observed_txs_keeps_first_duplicate_observation():
    observed_tx_id = 'DUPLICATE-OBS-TX'
    first_tx = _make_quorum_tx('native-1', observed_tx_id, memo='=:ETH.ETH:thor1first', from_address='first-source')
    second_tx = _make_quorum_tx('native-2', observed_tx_id, memo='=:ETH.ETH:thor1second', from_address='second-source')

    block = BlockResult(
        block_no=BLOCK_NO,
        txs=[first_tx, second_tx],
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
    )

    observed_txs = block.all_observed_txs

    assert len(observed_txs) == 1
    assert observed_txs[0].tx_id == observed_tx_id
    assert observed_txs[0].from_address == 'first-source'
    assert observed_txs[0].memo == '=:ETH.ETH:thor1first'

