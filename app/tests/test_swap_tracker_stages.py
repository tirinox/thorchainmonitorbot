"""
The stage of a tracked swap out of /thorchain/tx/status, and why it is late (models/swap_track.py).
"""
import pytest

from api.aionode.types import ThorConstants, ThorMimir, ThorTxStatus
from models.mimir import MimirHolder, MimirTuple
from models.s_swap import StreamingSwap
from models.swap_track import derive_stage, SwapStage, diagnose, DiagCtx, SwapTrack

TX = '27208951434B8D7ACB416C6B0B5DAE6449A3A3D2C4484F0B36803A180F24B1E3'
ZERO_ID = '0' * 64

# a real response of a finished RUNE -> SOL~SOL swap (thornode docs/examples/tutorials.md): no outbound stages at all
DONE_NATIVE = {
    'tx': {'id': TX, 'chain': 'THOR', 'from_address': 'thor17hwq', 'to_address': 'thor1g98c',
           'coins': [{'asset': 'THOR.RUNE', 'amount': '9671547414'}], 'gas': None,
           'memo': '=:SOL~SOL:thor17hwq:61140079/1/1'},
    'planned_out_txs': [{'chain': 'THOR', 'to_address': 'thor17hwq',
                         'coin': {'asset': 'SOL~SOL', 'amount': '61164077'}, 'refund': False}],
    'out_txs': [{'id': ZERO_ID, 'chain': 'THOR', 'from_address': 'thor1g98c', 'to_address': 'thor17hwq',
                 'coins': [{'asset': 'SOL~SOL', 'amount': '61164077'}], 'memo': f'OUT:{TX}'}],
    'stages': {
        'inbound_observed': {'final_count': 0, 'completed': True},
        'inbound_confirmation_counted': {'remaining_confirmation_seconds': 0, 'completed': True},
        'inbound_finalised': {'completed': True},
        'swap_status': {'pending': False},
        'swap_finalised': {'completed': True},
    },
}


def status(stages, out_txs=(), planned=()):
    return ThorTxStatus.from_json({'stages': stages, 'out_txs': list(out_txs), 'planned_out_txs': list(planned)})


OBSERVED = {'inbound_observed': {'completed': True}}
FINALISED = {**OBSERVED, 'inbound_confirmation_counted': {'completed': True}, 'inbound_finalised': {'completed': True}}
SWAPPED = {**FINALISED, 'swap_status': {'pending': False}, 'swap_finalised': {'completed': True}}

ETH_OUT = {'id': 'AB' * 32, 'chain': 'ETH', 'to_address': '0xdead', 'memo': f'OUT:{TX}',
           'coins': [{'asset': 'ETH.ETH', 'amount': '1837000000'}]}
BTC_REFUND = {'id': 'CD' * 32, 'chain': 'BTC', 'to_address': 'bc1qsender', 'memo': f'REFUND:{TX}',
              'coins': [{'asset': 'BTC.BTC', 'amount': '49970000'}]}


def test_native_output_is_done_without_outbound_stages():
    info = derive_stage(ThorTxStatus.from_json(DONE_NATIVE))
    assert info.stage == SwapStage.DONE and info.is_terminal
    assert info.out_txs[0]['coins'][0]['asset'] == 'SOL~SOL'


def test_confirmation_counting_is_observed_with_the_remaining_time():
    info = derive_stage(status({
        **OBSERVED,
        'inbound_confirmation_counted': {'chain': 'BTC', 'remaining_confirmation_seconds': 1200, 'completed': False},
    }))
    assert info.stage == SwapStage.OBSERVED
    assert info.confirmation_sec == info.expected_sec == 1200


def test_streaming_swap_in_the_queue_is_swapping():
    ss = StreamingSwap(tx_id=TX, interval=1, quantity=10, count=4, deposit=50_000_000, **{'in': 20_000_000, 'out': 7_36})
    info = derive_stage(status({**FINALISED, 'swap_status': {'pending': True}}), ss)
    assert info.stage == SwapStage.SWAPPING
    assert info.streaming is ss and info.expected_sec == ss.second_to_wait == 36.0


def test_legacy_queue_streaming_counts_come_from_the_status():
    info = derive_stage(status({**FINALISED,
                                'swap_status': {'pending': True, 'streaming': {'interval': 2, 'quantity': 5, 'count': 2}}}))
    assert info.stage == SwapStage.SWAPPING
    assert (info.streaming_count, info.streaming_quantity) == (2, 5)
    assert info.expected_sec == 3 * 2 * 6.0


def test_outbound_delay_then_signing_then_done():
    delayed = status({**SWAPPED,
                      'outbound_delay': {'remaining_delay_blocks': 120, 'remaining_delay_seconds': 720, 'completed': False},
                      'outbound_signed': {'scheduled_outbound_height': 1000, 'completed': False}})
    info = derive_stage(delayed)
    assert info.stage == SwapStage.OUTBOUND_DELAY
    assert info.outbound_delay_blocks == 120 and info.expected_sec == 720

    signing = status({**SWAPPED, 'outbound_delay': {'completed': True},
                      'outbound_signed': {'scheduled_outbound_height': 1000,
                                          'blocks_since_scheduled': {'value': 350}, 'completed': False}})
    info = derive_stage(signing)
    assert info.stage == SwapStage.OUTBOUND_SIGNING and info.blocks_since_scheduled == 350

    done = status({**SWAPPED, 'outbound_delay': {'completed': True}, 'outbound_signed': {'completed': True}},
                  out_txs=[ETH_OUT])
    assert derive_stage(done).stage == SwapStage.DONE


def test_finalised_swap_with_nothing_to_pay_is_flagged():
    # a real dust swap of a trade asset: the swap failed and the refund did not cover the fee, so nothing is planned
    info = derive_stage(status(SWAPPED))
    assert info.stage == SwapStage.SWAPPING and info.nothing_planned and not info.is_terminal
    # a native outbound just not out yet is not that
    planned = [{'chain': 'THOR', 'to_address': 'thor1', 'coin': {'asset': 'SOL~SOL', 'amount': '1'}, 'refund': False}]
    assert not derive_stage(status(SWAPPED, planned=planned)).nothing_planned
    assert SwapStage.FAILED in SwapStage.TERMINAL


def test_refund_and_partial_refund():
    signed = {**SWAPPED, 'outbound_delay': {'completed': True}, 'outbound_signed': {'completed': True}}
    assert derive_stage(status(signed, out_txs=[BTC_REFUND])).stage == SwapStage.REFUNDED
    assert derive_stage(status(signed, out_txs=[BTC_REFUND, ETH_OUT])).stage == SwapStage.PARTIAL_REFUND
    # a planned refund that is not out yet still tells the kind
    planned_refund = [{'chain': 'BTC', 'to_address': 'bc1q', 'coin': {'asset': 'BTC.BTC', 'amount': '1'}, 'refund': True}]
    assert derive_stage(status(signed, planned=planned_refund)).stage == SwapStage.REFUNDED


# ------------------------------------ diagnosis ------------------------------------

HEIGHT = 20_000_000


def mimir(**values):
    # the holder ignores an empty mimir or constants map, so there is always one entry of each
    holder = MimirHolder()
    return holder.update(MimirTuple(
        constants=ThorConstants.from_json({'int_64_values': {'EnableAdvSwapQueue': 0}}),
        mimir=ThorMimir.from_json({'HALTCHURNING': 0, **{k.upper(): v for k, v in values.items()}}),
        node_mimir={}, votes=[], thor_height=HEIGHT, ts=1.0,
    ), active_nodes=[])


def ctx(**values):
    return DiagCtx(src_chain='BTC', dst_chain='ETH', mimir=mimir(**values), thor_height=HEIGHT)


def test_halt_mimir_holds_a_height():
    m = mimir(HaltSigningETH=1, HaltBTCChain=HEIGHT + 100, NodePauseChainGlobal=HEIGHT + 50, HaltTrading=0)
    assert m.is_halt_active('HALTSIGNINGETH', HEIGHT)
    assert not m.is_halt_active('HALTBTCCHAIN', HEIGHT)  # scheduled for later
    assert m.is_halt_active('HALTBTCCHAIN', HEIGHT + 100)
    assert m.is_halt_active('NODEPAUSECHAINGLOBAL', HEIGHT)  # paused while the value is ahead
    assert not m.is_halt_active('NODEPAUSECHAINGLOBAL', HEIGHT + 51)
    assert not m.is_halt_active('HALTTRADING', HEIGHT)
    assert not m.is_halt_active('HALTETHTRADING', HEIGHT)  # unknown key


SIGNING = status({**SWAPPED, 'outbound_delay': {'completed': True},
                  'outbound_signed': {'blocks_since_scheduled': 10, 'completed': False}})


def test_a_halt_explains_the_delay_at_once_and_lifts():
    info = derive_stage(SIGNING)
    d = diagnose(info, ctx(HaltSigningETH=1), waited_sec=5, warn_after_sec=600)
    assert d.code == 'dst_signing_halted' and d.chain == 'ETH' and d.mimir_key == 'HALTSIGNINGETH' and d.is_halt
    assert diagnose(info, ctx(HaltSigningETH=0), waited_sec=5, warn_after_sec=600) is None


def test_overdue_without_a_halt():
    info = derive_stage(SIGNING)
    assert diagnose(info, ctx(), waited_sec=599, warn_after_sec=600) is None
    assert diagnose(info, ctx(), waited_sec=601, warn_after_sec=600).code == 'unknown'

    rescheduled = derive_stage(status({**SWAPPED, 'outbound_delay': {'completed': True},
                                       'outbound_signed': {'blocks_since_scheduled': {'value': 400}, 'completed': False}}))
    d = diagnose(rescheduled, ctx(), waited_sec=3000, warn_after_sec=600)
    assert d.code == 'rescheduled' and d.value == 400 and not d.is_halt


def test_inbound_side_halts_and_the_normal_confirmation_wait():
    confirming = derive_stage(status({**OBSERVED, 'inbound_confirmation_counted': {
        'remaining_confirmation_seconds': 1200, 'completed': False}}))
    # confirmations are not a delay: the expected time covers them
    assert diagnose(confirming, ctx(), waited_sec=1000, warn_after_sec=600) is None
    assert diagnose(confirming, ctx(HaltBTCChain=1), waited_sec=1, warn_after_sec=600).code == 'src_chain_halted'
    assert diagnose(confirming, ctx(HaltBTCTrading=1), waited_sec=1, warn_after_sec=600).code == 'src_trading_halted'
    assert diagnose(confirming, ctx(NodePauseChainGlobal=HEIGHT + 10), waited_sec=1,
                    warn_after_sec=600).mimir_key == 'NODEPAUSECHAINGLOBAL'


def test_stalled_thorchain_beats_everything_and_terminal_has_no_diagnosis():
    c = ctx(HaltSigningETH=1)
    c.thor_block_age_sec = 120
    assert diagnose(derive_stage(SIGNING), c, 1, 600).code == 'thor_stalled'
    assert diagnose(derive_stage(ThorTxStatus.from_json(DONE_NATIVE)), c, 1, 600) is None


def test_swap_track_round_trips_through_json():
    track = SwapTrack(tx_id=TX, users={'123': SwapTrack.ROLE_SENDER, '-45': SwapTrack.ROLE_RECIPIENT},
                      from_address='bc1qsender', dest_address='0xdead', in_asset='BTC.BTC', in_amount=50_000_000,
                      out_asset='ETH.ETH', volume_usd=52_400.0, memo_str='=:ETH.ETH:0xdead', start_height=HEIGHT,
                      started_ts=1.0)
    assert SwapTrack.from_json(track.to_json()) == track
    assert track.my_address('123') == 'bc1qsender' and track.my_address(-45) == '0xdead'
    assert (track.src_chain, track.dst_chain, track.in_amount_float) == ('BTC', 'ETH', 0.5)
