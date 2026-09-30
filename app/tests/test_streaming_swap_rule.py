import pytest

from api.aionode.types import ThorConstants, ThorMimir
from jobs.scanner.swap_props import SwapProps
from jobs.scanner.tx import ThorEvent
from models.events import EventSwap
from models.memo import ActionType, THORMemo
from models.mimir import MimirHolder, MimirTuple, adv_swap_queue_enabled
from models.s_swap import AlertSwapStart, is_streaming_swap
from models.tx import ThorAction, ThorMetaSwap, SUCCESS

# real mainnet memos (swap events of blocks 28002237 and 28005299)
NO_PARAMS = '=:ETH~USDP-0X8E870D67F660D95D5BE530380D0EC0BD388289E1:thor1fym5tc8henc7hwct9zae02wl5w6eextsx006ws:2863405117'
FORCED_SINGLE = '=:XRP~XRP:thor14mh37ua4vkyur0l5ra297a4la6tmf95mt96a55:23360176128/1/1'
AUTO_QUANTITY = '=:f:0x29717C8bb45C12B36FFD252C038213d17AE76932:4115378617/1/0:thor18dvgrgpvxlh7rhhld4qjyrxs9c7tvwdakrkjm4:60'
# from the replay of blocks 28040304..28040604
ONE_RAPID_SUB_SWAP = '=:ETH~ETH:thor166n4w5039meulfa3p6ydg60ve6ueac7tlt0jws:58121042/0/1'
RAPID_AUTO_QUANTITY = '=:AVAX.USDT:0x43bF5038ece030bCE993e17224EB54D556E1f5DA:306579400/0/0'


@pytest.mark.parametrize('interval, quantity, with_asq, classic', [
    (0, 1, False, False),  # no streaming params in the memo, or an explicit /0/1: one sub-swap
    (1, 1, False, False),  # explicit /1/1: a single swap in both queues
    (1, 0, True, True),  # the protocol picks the quantity
    (3, 0, True, True),
    (0, 0, True, False),  # interval 0: rapid streaming with the ASQ, a normal swap with the classic queue
    (0, 5, True, False),
    (3, 5, True, True),
    (None, None, False, False),
])
def test_rule(interval, quantity, with_asq, classic):
    assert is_streaming_swap(interval, quantity, adv_swap_queue=True) is with_asq
    assert is_streaming_swap(interval, quantity, adv_swap_queue=False) is classic


def _swap(memo, adv_swap_queue, is_streaming_swap_flag=False):
    return ThorAction(
        date_timestamp=0, height=1, status=SUCCESS, type=ActionType.SWAP.value, pools=[], in_tx=[], out_tx=[],
        meta_swap=ThorMetaSwap(liquidity_fee=0, network_fees=[], trade_slip=0, trade_target=0, memo=memo,
                               is_streaming_swap=is_streaming_swap_flag, adv_swap_queue=adv_swap_queue),
    )


@pytest.mark.parametrize('memo, with_asq, classic', [
    (NO_PARAMS, False, False),
    (FORCED_SINGLE, False, False),
    (ONE_RAPID_SUB_SWAP, False, False),
    (AUTO_QUANTITY, True, True),
    (RAPID_AUTO_QUANTITY, True, False),
])
def test_finished_swap(memo, with_asq, classic):
    assert _swap(memo, adv_swap_queue=True).is_streaming is with_asq
    assert _swap(memo, adv_swap_queue=False).is_streaming is classic


def test_swap_the_chain_split_by_itself_is_streaming():
    # a memo without parameters that the Advanced Swap Queue split into 2 sub-swaps (seen in block ~28039700)
    assert _swap(NO_PARAMS, adv_swap_queue=True, is_streaming_swap_flag=True).is_streaming is True


def _swap_props(memo, sub_swaps):
    events = [EventSwap.from_event(ThorEvent.from_dict({
        'type': 'swap', 'id': 'TX', 'pool': 'BSC.USDT', 'swap_target': '0', 'swap_slip': '0',
        'liquidity_fee': '0', 'liquidity_fee_in_rune': '0', 'emit_asset': '1 THOR.RUNE',
        'streaming_swap_quantity': str(sub_swaps), 'streaming_swap_count': str(i),
        'chain': 'BSC', 'from': '0xfrom', 'to': 'thor1to', 'coin': '100000000 BSC.USDT', 'memo': memo,
    }, height=100 + i)) for i in range(1, sub_swaps + 1)]
    attrs = {'id': 'TX', 'memo': memo, 'block_height': '100', 'in_amount': '100000000', 'in_asset': 'BSC.USDT',
             'from_address': '0xfrom'}
    return SwapProps(attrs, events, THORMemo.parse_memo(memo))


@pytest.mark.parametrize('sub_swaps, expected', [(1, False), (2, True)])
def test_finished_swap_counts_the_chains_sub_swaps(sub_swaps, expected):
    action = _swap_props(NO_PARAMS, sub_swaps).build_action(ts=1, adv_swap_queue=True)
    assert action.meta_swap.streaming.quantity == sub_swaps
    assert action.is_streaming is expected


def test_swap_from_midgard_uses_its_flag():
    # Midgard swaps do not know the queue mode, and they used to crash is_streaming
    assert _swap(NO_PARAMS, adv_swap_queue=None, is_streaming_swap_flag=True).is_streaming is True
    assert _swap(NO_PARAMS, adv_swap_queue=None, is_streaming_swap_flag=False).is_streaming is False


def test_malformed_memo_does_not_crash():
    assert _swap('=:BTC.BTC:bc1q::t:abc', adv_swap_queue=True).is_streaming is False


def test_not_a_swap_is_not_streaming():
    action = ThorAction(date_timestamp=0, height=1, status=SUCCESS, type=ActionType.ADD_LIQUIDITY.value,
                        pools=[], in_tx=[], out_tx=[])
    assert action.is_streaming is False


def _swap_start(memo_str, adv_swap_queue):
    memo = THORMemo.parse_memo(memo_str)
    return AlertSwapStart(
        tx_id='TX', from_address='thor1from', destination_address=memo.dest_address, in_amount=10 ** 8,
        in_asset='THOR.RUNE', out_asset=memo.asset, volume_usd=1.0, block_height=1, memo=memo, memo_str=memo_str,
        interval=memo.s_swap_interval, quantity=memo.s_swap_quantity, adv_swap_queue=adv_swap_queue,
    )


def test_swap_start():
    assert not _swap_start(NO_PARAMS, adv_swap_queue=True).is_streaming
    assert not _swap_start(FORCED_SINGLE, adv_swap_queue=True).is_streaming
    assert _swap_start(RAPID_AUTO_QUANTITY, adv_swap_queue=True).is_streaming
    assert not _swap_start(RAPID_AUTO_QUANTITY, adv_swap_queue=False).is_streaming
    assert _swap_start(AUTO_QUANTITY, adv_swap_queue=False).is_streaming


def _mimir(mimir_values):
    holder = MimirHolder()
    return holder.update(MimirTuple(
        constants=ThorConstants.from_json({'int_64_values': {'EnableAdvSwapQueue': 0}}),
        mimir=ThorMimir.from_json(mimir_values),
        node_mimir={}, votes=[], thor_height=1, ts=1.0,
    ), active_nodes=[])


def test_queue_mode_comes_from_mimir():
    assert adv_swap_queue_enabled(None) is True
    assert MimirHolder().adv_swap_queue_enabled is True  # not loaded yet
    assert _mimir({'ENABLEADVSWAPQUEUE': 1}).adv_swap_queue_enabled is True
    assert _mimir({'HALTTRADING': 0}).adv_swap_queue_enabled is False  # no Mimir override: the constant, 0
