"""
A tracked swap of a user: the record the tracker keeps in Redis, the stage derived from /thorchain/tx/status
and the diagnosis of a delay by the network state. Pure functions, no I/O: tests/test_swap_tracker_stages.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple

from api.aionode.types import ThorTxStatus, ThorLastBlock
from lib.constants import THOR_BLOCK_TIME, thor_to_float
from models.asset import Asset
from models.chains import ChainInfoHolder
from models.mimir import MimirHolder
from models.queue import QueueInfo
from models.s_swap import StreamingSwap


@dataclass
class SwapTrack:
    tx_id: str
    users: Dict[str, str]  # user_id -> ROLE_*
    from_address: str
    dest_address: str
    in_asset: str
    in_amount: int  # 1e8
    out_asset: str
    volume_usd: float
    memo_str: str
    start_height: int
    started_ts: float
    is_streaming: bool = False
    quantity: int = 1
    interval: int = 0
    expected_out: int = 0  # 1e8, by the quote at the start; 0 when the quote failed
    expected_sec: float = 0.0  # the whole swap by the quote
    stage: str = ''
    stage_since_ts: float = 0.0
    last_msg_ts: float = 0.0
    last_diag: str = ''
    last_diag_ts: float = 0.0
    next_poll_ts: float = 0.0
    polls: int = 0
    finish_attempts: int = 0  # waits for the block scanner to store the outbound before the final message
    known_start: bool = True  # False when /track met the swap already over: its duration is unknown

    ROLE_SENDER = 'sender'
    ROLE_RECIPIENT = 'recipient'
    ROLE_WATCHER = 'watcher'  # asked by /track: no address of the swap is known to be theirs

    @property
    def in_amount_float(self) -> float:
        return thor_to_float(self.in_amount)

    @property
    def expected_out_float(self) -> float:
        return thor_to_float(self.expected_out)

    @property
    def src_chain(self) -> str:
        return Asset(self.in_asset).chain

    @property
    def dst_chain(self) -> str:
        return Asset(self.out_asset).chain

    @property
    def has_outbound_stage(self) -> bool:
        """An L1 output waits for an outbound; RUNE, trade, synth and secured outputs are paid out at once"""
        a = Asset(self.out_asset)
        return not (a.is_trade or a.is_synth or a.is_secured or a.chain == 'THOR')

    def eta_sec(self, info: StageInfo, now: float) -> float:
        """Seconds to the end of the swap: the quote's total from the start, or what the stage itself says"""
        if info.is_terminal:
            return 0.0
        return max(info.expected_sec, self.expected_sec - (now - self.started_ts), 0.0)

    def my_address(self, user_id) -> str:
        """The address this user watches: the sender's or the recipient's; '' for a watcher"""
        role = self.users.get(str(user_id))
        if role == self.ROLE_RECIPIENT:
            return self.dest_address
        return self.from_address if role == self.ROLE_SENDER else ''

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, s: str) -> 'SwapTrack':
        return cls(**json.loads(s))


@dataclass
class SwapSummary:
    """What the user got for what, and what it cost; for the final message"""
    in_amount: float = 0.0
    in_asset: str = ''
    out_amount: float = 0.0
    out_asset: str = ''
    swap_value_usd: float = 0.0
    network_fees: List[Tuple[float, str, float]] = field(default_factory=list)  # (amount, asset, usd)
    liquidity_fee_rune: float = 0.0
    liquidity_fee_usd: float = 0.0
    # in the output asset by the affiliate_fee events; in RUNE when guessed from the affiliate's payout (old records)
    affiliate_fees: List[Tuple[float, str, float]] = field(default_factory=list)

    @property
    def network_fee_usd(self) -> float:
        return sum(usd for _, _, usd in self.network_fees)

    @property
    def affiliate_fee_usd(self) -> float:
        return sum(usd for _, _, usd in self.affiliate_fees)

    @property
    def total_fees_usd(self) -> float:
        return self.network_fee_usd + self.liquidity_fee_usd + self.affiliate_fee_usd

    @property
    def fees_percent(self) -> float:
        return 100.0 * self.total_fees_usd / self.swap_value_usd if self.swap_value_usd > 0 else 0.0

    @property
    def has_fees(self) -> bool:
        return bool(self.network_fees) or self.liquidity_fee_rune > 0 or bool(self.affiliate_fees)

    @property
    def rate(self) -> float:
        """Units of the output asset per one unit of the input asset"""
        return self.out_amount / self.in_amount if self.in_amount > 0 and self.out_amount > 0 else 0.0


def _first_out_to(outs: list, dest_address: str, refund: bool):
    """The out tx to the destination (case-insensitive: the memo has it as typed) or the first one of the kind"""
    outs = [o for o in outs if str(o.get('memo', '')).upper().startswith('REFUND') == refund]
    outs.sort(key=lambda o: str(o.get('to_address', '')).lower() != (dest_address or '').lower())
    return outs[0] if outs else None


def swap_summary(track: SwapTrack, info: StageInfo, action, ph) -> SwapSummary:
    """
    action: the ThorAction the block scanner built, with the fees; None when the scanner has not seen the swap.
    ph: the PriceHolder for the USD values (its convert_to_usd); the swap value is the input at today's price.
    """
    s = SwapSummary(in_amount=track.in_amount_float, in_asset=track.in_asset, out_asset=track.out_asset)

    def usd(amount, asset):
        try:
            return float(ph.convert_to_usd(amount, asset) or 0.0) if ph else 0.0
        except Exception:
            return 0.0

    if action is not None:
        in_tx = action.in_tx[0] if action.in_tx else None
        if in_tx and in_tx.coins:
            s.in_amount, s.in_asset = in_tx.coins[0].amount_float, in_tx.first_asset
        out = action.recipients_output
        if out and out.coins:
            s.out_amount, s.out_asset = out.coins[0].amount_float, out.first_asset
        meta = action.meta_swap
        if meta:
            # what the user paid: without the fee of the affiliate's conversion swap that Midgard counts in
            s.liquidity_fee_rune = thor_to_float(meta.liquidity_fee - (meta.affiliate_conversion_liquidity_fee or 0))
            s.network_fees = [(c.amount_float, c.asset, usd(c.amount_float, c.asset)) for c in meta.network_fees]
            if meta.affiliate_fees:
                s.affiliate_fees = [(c.amount_float, c.asset, usd(c.amount_float, c.asset))
                                    for c in meta.affiliate_fees]
        if not s.affiliate_fees:
            # a record from before the affiliate_fee events were kept: what the affiliate was paid in RUNE
            # (a swap to RUNE pays the affiliate by a plain transfer, so nothing is found for it here)
            paid = sum(c.amount_float for o in action.out_tx if o.is_affiliate for c in o.coins)
            if paid:
                s.affiliate_fees = [(paid, 'THOR.RUNE', usd(paid, 'THOR.RUNE'))]
    else:
        out = _first_out_to(info.out_txs, track.dest_address, refund=False)
        coin = (out.get('coins') or [{}])[0] if out else {}
        if coin:
            s.out_amount, s.out_asset = thor_to_float(coin.get('amount', 0)), coin.get('asset', s.out_asset)

    s.swap_value_usd = usd(s.in_amount, s.in_asset) or track.volume_usd
    s.liquidity_fee_usd = usd(s.liquidity_fee_rune, 'THOR.RUNE')
    return s


class SwapStage:
    OBSERVED = 'observed'  # inbound seen by the nodes, confirmations counting or not finalised yet
    SWAPPING = 'swapping'  # inbound finalised, the swap sits in the queue (streaming goes here)
    OUTBOUND_DELAY = 'outbound_delay'  # swapped, the outbound waits for its scheduled block
    OUTBOUND_SIGNING = 'outbound_signing'  # the block has come, the vault has not signed yet
    DONE = 'done'
    REFUNDED = 'refunded'
    PARTIAL_REFUND = 'partial_refund'  # streaming: part was swapped and sent, the rest returned
    # the swap is over and the network has nothing to pay out: it failed and the refund could not be made
    # (seen with dust: the refund does not cover the outbound fee). Set by the tracker after a grace period.
    FAILED = 'failed'

    TERMINAL = (DONE, REFUNDED, PARTIAL_REFUND, FAILED)
    # how long a stage normally lasts on top of what the status says; signing usually takes seconds
    ORDER = (OBSERVED, SWAPPING, OUTBOUND_DELAY, OUTBOUND_SIGNING)


@dataclass
class StageInfo:
    stage: str
    # how long the current stage is expected to last from now, by the status itself (0 = no idea)
    expected_sec: float = 0.0
    confirmation_sec: float = 0.0
    outbound_delay_blocks: int = 0
    blocks_since_scheduled: int = 0
    streaming: Optional[StreamingSwap] = None
    # of the legacy queue: count/quantity from swap_status.streaming when there is no StreamingSwap
    streaming_count: int = 0
    streaming_quantity: int = 0
    # the swap is finalised, yet the network plans no outbound at all (see SwapStage.FAILED)
    nothing_planned: bool = False
    out_txs: list = field(default_factory=list)
    planned_out_txs: list = field(default_factory=list)

    @property
    def is_terminal(self):
        return self.stage in SwapStage.TERMINAL


def _memo_kind(memo: str):
    memo = (memo or '').upper()
    if memo.startswith('REFUND:'):
        return 'refund'
    if memo.startswith('OUT:'):
        return 'out'
    return ''


def _int_value(v) -> int:
    # blocks_since_scheduled is a ProtoInt64 message {"value": N} in some versions, a plain int in others
    if isinstance(v, dict):
        v = v.get('value', 0)
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def derive_stage(status: ThorTxStatus, streaming: Optional[StreamingSwap] = None) -> StageInfo:
    info = _derive_stage(status, streaming)
    info.out_txs = status.out_txs or []
    info.planned_out_txs = status.planned_out_txs or []
    return info


def _derive_stage(status: ThorTxStatus, streaming: Optional[StreamingSwap]) -> StageInfo:
    stages = status.stages or {}
    observed = stages.get('inbound_observed') or {}
    confirmation = stages.get('inbound_confirmation_counted') or {}
    finalised = stages.get('inbound_finalised') or {}
    swap_status = stages.get('swap_status') or {}
    swap_finalised = stages.get('swap_finalised')
    outbound_delay = stages.get('outbound_delay')
    outbound_signed = stages.get('outbound_signed')

    out_txs = status.out_txs or []
    planned = status.planned_out_txs or []

    def terminal():
        kinds = {_memo_kind(t.get('memo')) for t in out_txs}
        kinds |= {'refund' if p.get('refund') else 'out' for p in planned}
        has_out, has_refund = 'out' in kinds, 'refund' in kinds
        if has_refund and not has_out:
            stage = SwapStage.REFUNDED
        elif has_refund and has_out:
            stage = SwapStage.PARTIAL_REFUND
        else:
            stage = SwapStage.DONE
        return StageInfo(stage)

    if not observed.get('completed') or not finalised.get('completed'):
        remaining = float(confirmation.get('remaining_confirmation_seconds', 0) or 0)
        if confirmation.get('completed'):
            remaining = 0.0
        return StageInfo(SwapStage.OBSERVED, expected_sec=remaining, confirmation_sec=remaining)

    if swap_status.get('pending'):
        legacy = swap_status.get('streaming') or {}
        expected = streaming.second_to_wait if streaming else 0.0
        if not expected and legacy:
            expected = (int(legacy.get('quantity', 0)) - int(legacy.get('count', 0))) * \
                       int(legacy.get('interval', 1) or 1) * THOR_BLOCK_TIME
        return StageInfo(
            SwapStage.SWAPPING, expected_sec=max(0.0, expected), streaming=streaming,
            streaming_count=int(legacy.get('count', 0)), streaming_quantity=int(legacy.get('quantity', 0)),
        )

    if outbound_signed is not None:
        # an L1 outbound: the two outbound stages exist
        if outbound_signed.get('completed'):
            return terminal()
        if outbound_delay and not outbound_delay.get('completed'):
            blocks = _int_value(outbound_delay.get('remaining_delay_blocks'))
            seconds = float(outbound_delay.get('remaining_delay_seconds', 0) or blocks * THOR_BLOCK_TIME)
            return StageInfo(SwapStage.OUTBOUND_DELAY, expected_sec=seconds, outbound_delay_blocks=blocks)
        return StageInfo(SwapStage.OUTBOUND_SIGNING,
                         blocks_since_scheduled=_int_value(outbound_signed.get('blocks_since_scheduled')))

    # RUNE or another native output: no outbound stages at all, the out tx appears at once
    if out_txs:
        return terminal()
    if swap_finalised is not None and not swap_finalised.get('completed'):
        return StageInfo(SwapStage.SWAPPING)
    # swap finalised, but no out txs yet: give it a block or two.
    # With nothing planned either, the network will pay nothing: the tracker turns this into FAILED after a while
    return StageInfo(SwapStage.SWAPPING, expected_sec=2 * THOR_BLOCK_TIME, nothing_planned=not planned)


# ------------------------------------ delay diagnosis ------------------------------------

@dataclass
class Diagnosis:
    code: str
    chain: str = ''
    value: float = 0.0  # a count, seconds or a block number, by the code
    mimir_key: str = ''

    # a halt lifts; the user gets a "resumed" message. Other causes just go away.
    HALT_CODES = ('thor_stalled', 'src_chain_halted', 'src_trading_halted', 'streaming_paused',
                  'trading_halted', 'dst_signing_halted', 'dst_chain_halted')

    @property
    def is_halt(self):
        return self.code in self.HALT_CODES


@dataclass
class DiagCtx:
    src_chain: str
    dst_chain: str
    mimir: Optional[MimirHolder] = None
    chain_info: Optional[ChainInfoHolder] = None
    queue: Optional[QueueInfo] = None
    last_blocks: Dict[str, ThorLastBlock] = field(default_factory=dict)
    thor_height: int = 0
    thor_block_age_sec: float = 0.0
    # the "congested" threshold of the public queue alert, so the two agree on what busy is
    queue_congested: int = 20
    # LackSigning reschedules an unsigned outbound after this many blocks (SigningTransactionPeriod)
    signing_period_blocks: int = 300

    def halt(self, key: str) -> bool:
        return bool(self.mimir and self.mimir.is_halt_active(key, self.thor_height))

    def chain_halted(self, chain: str) -> Optional[str]:
        """The mimir key (or 'inbound_addresses') that halts the chain, None when it runs"""
        if not chain or chain == 'THOR':
            return None
        for key in (f'HALT{chain}CHAIN', f'SOLVENCYHALT{chain}CHAIN', 'HALTCHAINGLOBAL', 'NODEPAUSECHAINGLOBAL'):
            if self.halt(key):
                return key
        info = self.chain_info.state_dict.get(chain) if self.chain_info else None
        if info is not None and info.halted:
            return 'inbound_addresses'
        return None

    def trading_halted(self, chain: str) -> Optional[str]:
        for key in (f'HALT{chain}TRADING', 'HALTTRADING'):
            if chain and self.halt(key):
                return key
        if self.chain_info and chain and self.chain_info.trading_paused(chain):
            return 'inbound_addresses'
        return None

    def signing_halted(self, chain: str) -> Optional[str]:
        for key in (f'HALTSIGNING{chain}', 'HALTSIGNING'):
            if chain and self.halt(key):
                return key
        return None


def diagnose(info: StageInfo, ctx: DiagCtx, waited_sec: float, warn_after_sec: float) -> Optional[Diagnosis]:
    """
    Why does the swap sit in its stage? None while it is not overdue or when it is done.
    The first matching rule wins; "unknown" when it is overdue and nothing explains it.
    """
    if info.is_terminal:
        return None

    if ctx.thor_block_age_sec > 60:
        return Diagnosis('thor_stalled', value=ctx.thor_block_age_sec)

    stage = info.stage
    src, dst = ctx.src_chain, ctx.dst_chain

    if stage == SwapStage.OBSERVED:
        if key := ctx.chain_halted(src):
            return Diagnosis('src_chain_halted', src, mimir_key=key)
        if key := ctx.trading_halted(src):
            return Diagnosis('src_trading_halted', src, mimir_key=key)

    elif stage == SwapStage.SWAPPING:
        if (info.streaming or info.streaming_quantity > 1) and ctx.halt('STREAMINGSWAPPAUSE'):
            return Diagnosis('streaming_paused', mimir_key='STREAMINGSWAPPAUSE')
        for chain in (src, dst):
            if key := ctx.trading_halted(chain):
                return Diagnosis('trading_halted', chain, mimir_key=key)

    elif stage == SwapStage.OUTBOUND_SIGNING:
        if key := ctx.signing_halted(dst):
            return Diagnosis('dst_signing_halted', dst, mimir_key=key)
        if key := ctx.chain_halted(dst):
            return Diagnosis('dst_chain_halted', dst, mimir_key=key)

    if waited_sec <= info.expected_sec + warn_after_sec:
        return None  # still within the normal time, and no halt is in the way

    if stage == SwapStage.OUTBOUND_SIGNING:
        if ctx.queue and ctx.queue.outbound >= ctx.queue_congested:
            return Diagnosis('outbound_queue_busy', dst, value=ctx.queue.outbound)
        if info.blocks_since_scheduled > ctx.signing_period_blocks:
            return Diagnosis('rescheduled', dst, value=info.blocks_since_scheduled)

    return Diagnosis('unknown')
