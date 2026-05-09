from types import SimpleNamespace

import pytest

from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.swap_start_detector import SwapStartDetectorFromBlock
from jobs.scanner.tx import NativeThorTx, ThorTxMessage, ThorMessageType
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from models.memo import THORMemo, ActionType
from models.s_swap import AlertSwapStart
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tests.fakes import FakeDB, make_price_holder


class FakeCfg:
    def __init__(self, *, max_age='2d', min_streaming_swap_usd=100.0, hide_arb_bots=False):
        self.tx = SimpleNamespace(max_age=max_age)
        self._values = {
            'tx.swap.also_trigger_when.streaming_swap.volume_greater': min_streaming_swap_usd,
            'tx.swap.hide_arbitrage_bots': hide_arb_bots,
        }

    def _get(self, path, default=None):
        return self._values.get(path, default)

    def as_float(self, path, default=0.0):
        return float(self._get(path, default))

    def as_bool(self, path, default=False):
        value = self._get(path, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {'', '0', 'false', 'none', 'null', 'no'}

    def as_int(self, path, default=0):
        return int(self._get(path, default))


class FakeLastBlockCache:
    def __init__(self, height):
        self.height = height

    async def get_thor_block(self):
        return self.height


class FakeRefMemoCache:
    async def get_memo(self, reference_id):
        return ''


def make_deps(*, max_age='2d', last_block=1_000_000) -> DepContainer:
    deps = DepContainer()
    deps.db = FakeDB()
    deps.cfg = FakeCfg(max_age=max_age)
    deps.last_block_cache = FakeLastBlockCache(last_block)
    deps.ref_memo_cache = FakeRefMemoCache()
    return deps


def make_event(*, tx_id='stream-tx', block_height=1_000_000, volume_usd=10_000.0) -> AlertSwapStart:
    return AlertSwapStart(
        tx_id=tx_id,
        from_address='thor1senderaddress0000000000000000000000000000000',
        destination_address='thor1destination0000000000000000000000000000',
        in_amount=100_000_000,
        in_asset='BTC.BTC',
        out_asset='ETH.ETH',
        volume_usd=volume_usd,
        block_height=block_height,
        memo=THORMemo(action=ActionType.SWAP, affiliates=[]),
        memo_str='=:ETH.ETH:0xabc',
        quantity=3,
        interval=10,
        is_limit=False,
    )


def make_observed_quorum_native_tx_from_sample() -> NativeThorTx:
    msg = ThorTxMessage.from_dict({
        '@type': ThorMessageType.MsgObservedTxQuorum.value,
        'quoTx': {
            'obsTx': {
                'tx': {
                    'id': '54F2B5075E6CAA7B2D3363A77C3384CAF8B9C3C448B8C04E1C0409016CAD6C2F',
                    'chain': 'ETH',
                    'from_address': '0x673157751f6f3debaae977a9489d8af285837de6',
                    'to_address': '0x87fe857d8a5a8dE742E8aB4928e517f7F3B3C6E4',
                    'coins': [{
                        'asset': 'ETH.ETH',
                        'amount': '48118900000',
                        'decimals': '0',
                    }],
                    'gas': [{
                        'asset': 'ETH.ETH',
                        'amount': '409',
                        'decimals': '0',
                    }],
                    'memo': '=:b:bc1qz3tklehg7qrffz6ga82zqxgn5sf07r2s5nvwsp:1387943334/1/0:dx:30',
                },
                'status': 'incomplete',
                'out_hashes': [],
                'block_height': '24814698',
                'signers': [],
                'observed_pub_key': 'thorpub1addwnpepqg8j0wznyt9spxss75mg3ngcapwcmt6s6zkw2rrngmwgewg8xfz7jc8v4jh',
                'keysign_ms': '0',
                'finalise_height': '24814698',
                'aggregator': '',
                'aggregator_target': '',
                'aggregator_target_limit': None,
            },
            'attestations': [{
                'PubKey': 'ArCdE7cjNiXXsh9NLAqxVUwaEUdnjsC6S4+TBQh2CkPM',
                'Signature': 'joq6gz1r3bT+9OUPc3CIl2wMpjdJbm2QCqbjUaGH3mtb51jfk6bybfAKKHHVo1IaivfHHbVCyv/9uHvJ35AABQ==',
            }],
            'inbound': True,
            'allow_future_observation': False,
        },
        'signer': 'thor1zxhfu0qmmq6gmgq4sgz0xgq69h0nhqx5yrseu5',
    })
    return NativeThorTx(
        tx_hash='400EBAEFBB37E5F626988CFCC5AEEE107625672585F9B1CCDD0F130F84AA8B23',
        code=0,
        events=[],
        height=26_101_907,
        original={},
        signers=[],
        messages=[msg],
        memo='',
        timestamp=1_746_792_623,
    )


def make_block(*txs, block_no=26_101_907) -> BlockResult:
    return BlockResult(
        block_no=block_no,
        txs=list(txs),
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
        timestamp=1_746_792_623,
    )


@pytest.mark.asyncio
async def test_streaming_swap_start_accepts_recent_swap():
    deps = make_deps(max_age='2d', last_block=1_000_000)
    notifier = StreamingSwapStartTxNotifier(deps)

    recent_gap_blocks = int(parse_timespan_to_seconds('1d') / notifier.thor_block_time_sec)
    event = make_event(block_height=1_000_000 - recent_gap_blocks)

    assert await notifier.is_swap_eligible(event) is True


@pytest.mark.asyncio
async def test_streaming_swap_start_rejects_stale_swap():
    deps = make_deps(max_age='2d', last_block=1_000_000)
    notifier = StreamingSwapStartTxNotifier(deps)

    stale_gap_blocks = int(parse_timespan_to_seconds('3d') / notifier.thor_block_time_sec)
    event = make_event(block_height=1_000_000 - stale_gap_blocks)

    assert await notifier.is_swap_eligible(event) is False


@pytest.mark.asyncio
async def test_streaming_swap_start_disables_age_filter_when_max_age_is_zero():
    deps = make_deps(max_age='0', last_block=1_000_000)
    notifier = StreamingSwapStartTxNotifier(deps)
    event = make_event(block_height=1)

    assert await notifier.is_swap_eligible(event) is True


@pytest.mark.asyncio
async def test_observed_quorum_swap_uses_original_observed_block_height_and_is_filtered_by_notify():
    deps = make_deps(max_age='2d', last_block=26_101_907)
    detector = SwapStartDetectorFromBlock(deps)
    notifier = StreamingSwapStartTxNotifier(deps)
    block = make_block(make_observed_quorum_native_tx_from_sample(), block_no=26_101_907)

    swaps = await detector.detect_swaps(block, make_price_holder())

    assert len(swaps) == 1
    event = swaps[0]
    assert event.tx_id == '54F2B5075E6CAA7B2D3363A77C3384CAF8B9C3C448B8C04E1C0409016CAD6C2F'
    assert event.block_height == 24_814_698
    assert event.block_height != block.block_no

    assert await notifier.is_swap_eligible(event) is False


