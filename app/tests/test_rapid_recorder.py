import pytest

from jobs.rapid_recorder import RapidSwapRecorder
from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.tx import ThorEvent
from lib.depcont import DepContainer


def make_swap_event(tx_id: str, height: int, pool: str = 'BTC.BTC'):
    return ThorEvent.from_dict({
        'type': 'swap',
        'id': tx_id,
        'pool': pool,
        'swap_target': '0',
        'swap_slip': '0',
        'liquidity_fee': '0',
        'liquidity_fee_in_rune': '0',
        'emit_asset': '1 THOR.RUNE',
        'streaming_swap_quantity': '1',
        'streaming_swap_count': '1',
        'chain': 'THOR',
        'from': 'thor1from',
        'to': 'thor1to',
        'coin': '1 BTC.BTC',
        'memo': 'SWAP:THOR.RUNE:thor1to',
    }, height=height)


def make_outbound_event(tx_id: str, height: int):
    return ThorEvent.from_dict({
        'type': 'outbound',
        'in_tx_id': tx_id,
        'id': f'out-{tx_id}',
        'chain': 'BTC',
        'from': 'thor1module',
        'to': 'bc1dest',
        'coin': '1 BTC.BTC',
        'memo': f'OUT:{tx_id}',
    }, height=height)


def make_block(*events, block_no: int = 123):
    return BlockResult(
        block_no=block_no,
        txs=[],
        end_block_events=list(events),
        begin_block_events=[],
        error=ScannerError(0, ''),
        timestamp=1_700_000_000,
    )


def test_collect_rapid_swap_candidates_finds_duplicate_swap_tx_ids_in_same_block():
    recorder = RapidSwapRecorder(DepContainer())
    block = make_block(
        make_swap_event('rapid-1', 123, pool='BSC.USDT-0xabc'),
        make_swap_event('rapid-1', 123, pool='BASE.ETH'),
        make_swap_event('normal-1', 123, pool='ETH.ETH'),
        make_outbound_event('rapid-1', 123),
    )

    candidates = recorder.collect_rapid_swap_candidates(block)

    assert list(candidates.keys()) == ['rapid-1']
    assert len(candidates['rapid-1']) == 2


@pytest.mark.asyncio
async def test_on_data_accepts_block_result_and_stores_last_candidates():
    recorder = RapidSwapRecorder(DepContainer())
    block = make_block(
        make_swap_event('rapid-2', 555, pool='BSC.USDT-0xabc'),
        make_swap_event('rapid-2', 555, pool='BASE.ETH'),
        block_no=555,
    )

    await recorder.on_data(None, block)

    assert recorder.last_seen_block_no == 555
    assert 'rapid-2' in recorder.last_rapid_candidates
    assert len(recorder.last_rapid_candidates['rapid-2']) == 2

