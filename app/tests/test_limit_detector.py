import pytest

from jobs.scanner.limit_detector import LimitSwapDetector, LimitSwapBlockUpdate
from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.tx import NativeThorTx, ThorEvent
from lib.delegates import INotified
from lib.depcont import DepContainer


def make_event(ev_type: str, memo: str = None):
    d = {'type': ev_type}
    if memo is not None:
        d['memo'] = memo
    return ThorEvent.from_dict(d)


def make_tx(memo: str):
    return NativeThorTx(
        tx_hash='tx-hash',
        code=0,
        events=[],
        height=12345,
        original={},
        signers=[],
        messages=[],
        memo=memo,
        timestamp=0,
    )


def test_get_swap_limit_end_block_events():
    # Prepare block with mixed end_block_events
    ev1 = make_event('swap', memo='=<:b:addr:1000000/100800/0')  # should match
    ev2 = make_event('swap', memo='=:notlimit:')  # not a limit memo
    ev3 = make_event('limit_swap_close', memo='something')  # not type 'swap'
    ev4 = make_event('swap', memo=None)  # missing memo

    block = BlockResult(block_no=12345, txs=[], end_block_events=[ev1, ev2, ev3, ev4], begin_block_events=[], error=ScannerError(0, ''))

    found = list(LimitSwapDetector.get_swap_limit_end_block_events(block))
    assert len(found) == 1
    assert found[0].type == 'swap'
    assert found[0].attrs.get('memo').startswith('=<')


def test_get_limit_swap_close_end_block_events():
    ev1 = make_event('swap', memo='=<:b:addr:1000000/100800/0')
    ev2 = make_event('limit_swap_close', memo='close')
    ev3 = make_event('limit_swap_close', memo='close2')

    block = BlockResult(
        block_no=12345,
        txs=[],
        end_block_events=[ev1, ev2, ev3],
        begin_block_events=[],
        error=ScannerError(0, ''),
    )

    found = list(LimitSwapDetector.get_limit_swap_close_end_block_events(block))
    assert len(found) == 2
    assert all(ev.type == 'limit_swap_close' for ev in found)


def test_get_limit_swap_txs():
    tx1 = make_tx('=<:BTC.BTC:bc1qfoo:1000000/100800/0')
    tx2 = make_tx('m=<:1234BTC.BTC:5678ETH.ETH:2500000000')
    tx3 = make_tx('=:BTC.BTC:bc1qbar:1000000')
    tx4 = make_tx('')

    block = BlockResult(
        block_no=12345,
        txs=[tx1, tx2, tx3, tx4],
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
    )

    found = list(LimitSwapDetector.get_limit_swap_txs(block))
    assert found == [tx1, tx2]


def test_get_new_opened_limit_swap_txs():
    tx1 = make_tx('=<:BTC.BTC:bc1qfoo:1000000/100800/0')
    tx2 = make_tx('m=<:1234BTC.BTC:5678ETH.ETH:2500000000')
    tx3 = make_tx('=:BTC.BTC:bc1qbar:1000000')

    block = BlockResult(
        block_no=12345,
        txs=[tx1, tx2, tx3],
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
    )

    found = list(LimitSwapDetector.get_new_opened_limit_swap_txs(block))
    assert found == [tx1]


def test_get_limit_swap_close_reason():
    ev1 = make_event('limit_swap_close')
    ev1.attrs['reason'] = 'Limit swap expired by TTL'

    ev2 = make_event('limit_swap_close')
    ev2.attrs['reason'] = 'swap has been completed.'

    ev3 = make_event('limit_swap_close')
    ev3.attrs['reason'] = 'limit swap cancelled by user'

    ev4 = make_event('limit_swap_close')
    ev4.attrs['message'] = 'limit swap failed due to conditions'

    assert LimitSwapDetector.get_limit_swap_close_reason(ev1) == LimitSwapDetector.REASON_EXPIRED
    assert LimitSwapDetector.get_limit_swap_close_reason(ev2) == LimitSwapDetector.REASON_COMPLETED
    assert LimitSwapDetector.get_limit_swap_close_reason(ev3) == LimitSwapDetector.REASON_CANCELLED
    assert LimitSwapDetector.get_limit_swap_close_reason(ev4) == ''


class Collector(INotified):
    def __init__(self):
        self.items = []

    async def on_data(self, sender, data):
        self.items.append(data)


@pytest.mark.asyncio
async def test_on_data_emits_structured_payload():
    tx_open = make_tx('=<:BTC.BTC:bc1qfoo:1000000/100800/0')
    tx_modify = make_tx('m=<:1234BTC.BTC:5678ETH.ETH:2500000000')

    partial = make_event('swap', memo='=<:BTC.BTC:bc1qfoo:1000000/100800/0')
    close = make_event('limit_swap_close')
    close.attrs['reason'] = 'limit swap failed due to conditions'

    block = BlockResult(
        block_no=777,
        txs=[tx_open, tx_modify],
        end_block_events=[partial, close],
        begin_block_events=[],
        error=ScannerError(0, ''),
    )

    detector = LimitSwapDetector(DepContainer())
    collector = Collector()
    detector.add_subscriber(collector)

    await detector.on_data(None, block)

    assert len(collector.items) == 1
    payload = collector.items[0]
    assert isinstance(payload, LimitSwapBlockUpdate)
    assert payload.block_no == 777
    assert payload.new_opened_limit_swaps == [tx_open]
    assert len(payload.closed_limit_swaps) == 1
    assert payload.closed_limit_swaps[0].event == close
    assert payload.closed_limit_swaps[0].reason == LimitSwapDetector.REASON_FAILED
    assert payload.partial_swaps == [partial]


