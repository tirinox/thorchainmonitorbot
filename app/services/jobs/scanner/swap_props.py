import json
from datetime import datetime
from typing import NamedTuple, List, Optional

from proto.access import DecodedEvent
from services.lib.memo import THORMemo
from services.lib.money import is_rune_asset
from services.models.s_swap import TypeEventSwapAndOut, parse_swap_and_out_event, EventStreamingSwap, StreamingSwap, \
    EventSwap
from services.models.tx import ThorTx, SUCCESS, ThorMetaSwap, ThorTxType


class SwapProps(NamedTuple):
    attrs: dict
    events: List[TypeEventSwapAndOut]
    memo: THORMemo

    @classmethod
    def restore_events_from_tx_status(cls, attrs):
        """
            foo = await self.read_tx_status(swap_ev.tx_id)
            foo_ev = self.restore_events_from_tx_status(foo)
        """
        results = []
        key: str
        for key, value in attrs.items():
            if key.startswith('ev_'):
                raw_dict = json.loads(value)
                event = DecodedEvent.from_dict_our(raw_dict)
                swap_ev = parse_swap_and_out_event(event)
                results.append(swap_ev)

        return cls(
            attrs,
            results,
            memo=THORMemo.parse_memo(attrs.get('memo', ''))
        )

    @property
    def is_streaming(self):
        return bool(self.attrs.get('is_streaming', False))

    def find_event(self, klass) -> Optional[TypeEventSwapAndOut]:
        return next(self.find_events(klass), None)

    def find_events(self, klass):
        return (e for e in self.events if isinstance(e, klass))

    @property
    def is_streaming_finished(self):
        ss = self.find_event(EventStreamingSwap)
        return ss and ss.streaming_swap_count == ss.streaming_swap_quantity > 1

    @property
    def is_native_outbound(self):
        out_asset = self.memo.asset
        return '/' in out_asset or is_rune_asset(out_asset)

    def build_tx(self) -> ThorTx:
        attrs = self.attrs

        memo_str = self.attrs.get('memo', '')
        height = int(attrs.get('block_height', 0))
        tx_id = attrs.get('id')

        swaps: List[EventSwap] = list(self.find_events(EventSwap))
        pools = []
        for swap in swaps:
            if swap.pool not in pools:
                pools.append(swap.pool)

        in_tx = []  # todo
        out_tx = []  # todo
        slip = 0  # todo
        affiliate_fee = 0  # todo
        liquidity_fee = 0  # todo
        trade_target = 0  # todo
        affiliate_address = ''  # todo
        network_fees = []  # todo

        ss = StreamingSwap(  # todo
            tx_id=tx_id,
            interval=0,
            quantity=0,
            count=0,
            last_height=0,
            trade_target=0,
            deposit=0,
            in_amt=0,
            out_amt=0,
            failed_swaps=[],
            failed_swap_reasons=[]
        )

        tx = ThorTx(
            date=int(datetime.utcnow().timestamp() * 1e9),
            height=height,
            type=ThorTxType.TYPE_SWAP,
            pools=pools,
            in_tx=in_tx,
            out_tx=out_tx,
            meta_swap=ThorMetaSwap(
                liquidity_fee=liquidity_fee,
                network_fees=network_fees,
                trade_slip=slip,
                trade_target=trade_target,
                affiliate_fee=affiliate_fee,
                memo=memo_str,
                affiliate_address=affiliate_address,
                streaming=ss
            ),
            status=SUCCESS
        )
        return tx
