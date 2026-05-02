import pytest

from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.swap_start_detector import SwapStartDetectorFromBlock
from jobs.scanner.tx import NativeThorTx, ThorTxMessage, ThorMessageType
from lib.depcont import DepContainer
from models.memo import ActionType
from tests.fakes import make_price_holder


class FakeRefMemoCache:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.calls = []

    async def get_memo(self, reference_id):
        self.calls.append(reference_id)
        return self.mapping.get(int(reference_id), '')

def make_observed_quorum_native_tx(tx_id: str, memo: str, amount: int, asset: str = 'BTC.BTC') -> NativeThorTx:
    msg = ThorTxMessage.from_dict({
        '@type': ThorMessageType.MsgObservedTxQuorum.value,
        'quoTx': {
            'obsTx': {
                'tx': {
                    'id': tx_id,
                    'chain': 'BTC',
                    'from_address': 'bc1from',
                    'to_address': 'thor1vault',
                    'coins': [{
                        'asset': asset,
                        'amount': str(amount),
                        'decimals': '8',
                    }],
                    'gas': [],
                    'memo': memo,
                },
                'status': 'incomplete',
                'out_hashes': [],
                'block_height': '25621817',
                'finalise_height': '25621817',
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
        height=25621817,
        original={},
        signers=[],
        messages=[msg],
        memo='',
        timestamp=1_700_000_000,
    )


def make_block(*txs) -> BlockResult:
    return BlockResult(
        block_no=25621817,
        txs=list(txs),
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
        timestamp=1_700_000_000,
    )


def make_detector(cache_mapping=None) -> tuple[SwapStartDetectorFromBlock, FakeRefMemoCache]:
    deps = DepContainer()
    fake_cache = FakeRefMemoCache(cache_mapping)
    deps.ref_memo_cache = fake_cache
    detector = SwapStartDetectorFromBlock(deps)
    return detector, fake_cache


@pytest.mark.asyncio
async def test_detect_swaps_resolves_use_reference_memo_from_cache():
    resolved_memo = '=:ETH.ETH:0xabc:1000'
    detector, cache = make_detector({11791: resolved_memo})
    block = make_block(make_observed_quorum_native_tx('obs-ref', 'R:11791', 123456789))

    swaps = await detector.detect_swaps(block, make_price_holder())

    assert len(swaps) == 1
    assert swaps[0].tx_id == 'obs-ref'
    assert swaps[0].memo_str == resolved_memo
    assert swaps[0].memo.action == ActionType.SWAP
    assert swaps[0].out_asset == 'ETH.ETH'
    assert cache.calls == [11791]


@pytest.mark.asyncio
async def test_detect_swaps_resolves_missing_memo_from_last_five_digits_of_amount():
    resolved_memo = '=:ETH.ETH:0xdef:1000'
    detector, cache = make_detector({11791: resolved_memo})
    block = make_block(make_observed_quorum_native_tx('obs-empty', '', 9999911791))

    swaps = await detector.detect_swaps(block, make_price_holder())

    assert len(swaps) == 1
    assert swaps[0].tx_id == 'obs-empty'
    assert swaps[0].memo_str == resolved_memo
    assert swaps[0].memo.action == ActionType.SWAP
    assert cache.calls == [11791]


@pytest.mark.asyncio
async def test_detect_swaps_skips_observed_tx_when_reference_memo_cannot_be_resolved():
    detector, cache = make_detector({})
    block = make_block(make_observed_quorum_native_tx('obs-miss', '', 1234511791))

    swaps = await detector.detect_swaps(block, make_price_holder())

    assert swaps == []
    assert cache.calls == [11791]
