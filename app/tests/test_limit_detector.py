import pytest

from jobs.scanner.limit_detector import LimitSwapDetector, LimitSwapBlockUpdate, OpenedLimitSwap
from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.tx import NativeThorTx, ThorEvent, ThorTxMessage, ThorMessageType
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


def make_deposit_tx(tx_hash: str, memo: str, asset: str = 'BTC.BTC', amount: int = 100_000_000, signer: str = 'thor1alice'):
    msg = ThorTxMessage.from_dict({
        '@type': ThorMessageType.MsgDeposit.value,
        'coins': [{'asset': asset, 'amount': str(amount)}],
        'signer': signer,
    })
    return NativeThorTx(
        tx_hash=tx_hash,
        code=0,
        events=[],
        height=12345,
        original={},
        signers=[],
        messages=[msg],
        memo=memo,
        timestamp=0,
    )


def make_observed_quorum_tx(tx_id: str, memo: str, asset: str = 'ETH.ETH', amount: int = 200_000_000, decimals: int = 18,
                            from_address: str = '0xalice'):
    msg = ThorTxMessage.from_dict({
        '@type': ThorMessageType.MsgObservedTxQuorum.value,
        'quoTx': {
            'obsTx': {
                'tx': {
                    'id': tx_id,
                    'chain': 'ETH',
                    'from_address': from_address,
                    'to_address': 'thor1vault',
                    'coins': [{
                        'asset': asset,
                        'amount': str(amount),
                        'decimals': str(decimals),
                    }],
                    'gas': [],
                    'memo': memo,
                },
                'status': 'incomplete',
                'out_hashes': [],
                'block_height': '24792173',
                'finalise_height': '24792173',
                'aggregator': '',
                'aggregator_target': '',
                'aggregator_target_limit': None,
            },
            'inbound': True,
        },
    })
    return NativeThorTx(
        tx_hash=f'native-{tx_id}',
        code=0,
        events=[],
        height=12345,
        original={},
        signers=[],
        messages=[msg],
        memo='',
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
    tx1 = make_deposit_tx('native-open', '=<:BTC.BTC:bc1qfoo:1000000/100800/0', asset='BTC.BTC', amount=100_000_000,
                          signer='thor1native')
    tx2 = make_deposit_tx('native-modify', 'm=<:1234BTC.BTC:5678ETH.ETH:2500000000')
    tx3 = make_deposit_tx('native-swap', '=:BTC.BTC:bc1qbar:1000000')
    tx4 = make_observed_quorum_tx('observed-open', '=<:BTC.BTC:bc1qfoo:1000000/100800/0', amount=200_000_000, decimals=18,
                                  from_address='0xobserved')
    tx5 = make_observed_quorum_tx('observed-modify', 'm=<:200000000ETH.USDC-0XABC:98900ETH.ETH:0')

    block = BlockResult(
        block_no=12345,
        txs=[tx1, tx2, tx3, tx4, tx5],
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
    )

    found = list(LimitSwapDetector.get_new_opened_limit_swap_txs(block))
    assert found == [
        OpenedLimitSwap(
            tx_id='native-open',
            memo='=<:BTC.BTC:bc1qfoo:1000000/100800/0',
            source_asset='BTC.BTC',
            source_amount=100_000_000,
            source_amount_float=1.0,
            source_decimals=8,
            trader='thor1native',
            target_asset='BTC.BTC',
            thor_block_no=12345,
        ),
        OpenedLimitSwap(
            tx_id='observed-open',
            memo='=<:BTC.BTC:bc1qfoo:1000000/100800/0',
            source_asset='ETH.ETH',
            source_amount=200_000_000,
            source_amount_float=2.0,
            source_decimals=18,
            trader='0xobserved',
            target_asset='BTC.BTC',
            thor_block_no=12345,
        ),
    ]


def test_observed_limit_swap_ignores_reference_decimals_for_amount_calculation():
    tx = make_observed_quorum_tx(
        'observed-open',
        '=<:THOR.RUNE:thor1dest:1000000/100800/0',
        asset='ETH.USDT-0XABC',
        amount=3_452_170_000_000,
        decimals=6,
        from_address='0xobserved',
    )

    block = BlockResult(
        block_no=12345,
        txs=[tx],
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
    )

    opened = LimitSwapDetector._make_opened_limit_swap_from_observed_tx(block.all_observed_txs[0], thor_block_no=12345)

    assert opened == OpenedLimitSwap(
        tx_id='observed-open',
        memo='=<:THOR.RUNE:thor1dest:1000000/100800/0',
        source_asset='ETH.USDT-0XABC',
        source_amount=3_452_170_000_000,
        source_amount_float=34_521.7,
        source_decimals=6,
        trader='0xobserved',
        target_asset='THOR.RUNE',
        thor_block_no=12345,
    )


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
    tx_open = make_deposit_tx('native-open', '=<:BTC.BTC:bc1qfoo:1000000/100800/0', asset='BTC.BTC', amount=100_000_000,
                              signer='thor1native')
    tx_modify = make_deposit_tx('native-modify', 'm=<:1234BTC.BTC:5678ETH.ETH:2500000000')
    tx_observed = make_observed_quorum_tx('observed-open', '=<:ETH.ETH:0xfoo:1000000/100800/0', asset='ETH.ETH',
                                          amount=200_000_000, decimals=18, from_address='0xobserved')

    partial = make_event('swap', memo='=<:BTC.BTC:bc1qfoo:1000000/100800/0')
    close = make_event('limit_swap_close')
    close.attrs['reason'] = 'limit swap failed due to conditions'

    block = BlockResult(
        block_no=777,
        txs=[tx_open, tx_modify, tx_observed],
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
    assert payload.new_opened_limit_swaps == [
        OpenedLimitSwap(
            tx_id='native-open',
            memo='=<:BTC.BTC:bc1qfoo:1000000/100800/0',
            source_asset='BTC.BTC',
            source_amount=100_000_000,
            source_amount_float=1.0,
            source_decimals=8,
            trader='thor1native',
            target_asset='BTC.BTC',
            thor_block_no=12345,
        ),
        OpenedLimitSwap(
            tx_id='observed-open',
            memo='=<:ETH.ETH:0xfoo:1000000/100800/0',
            source_asset='ETH.ETH',
            source_amount=200_000_000,
            source_amount_float=2.0,
            source_decimals=18,
            trader='0xobserved',
            target_asset='ETH.ETH',
            thor_block_no=777,
        ),
    ]
    assert len(payload.closed_limit_swaps) == 1
    assert payload.closed_limit_swaps[0].event == close
    assert payload.closed_limit_swaps[0].reason == LimitSwapDetector.REASON_FAILED
    assert payload.partial_swaps == [partial]

