import json
from datetime import datetime
from typing import NamedTuple, List, Optional, Tuple

from proto.access import DecodedEvent
from services.lib.memo import THORMemo
from services.lib.money import is_rune_asset
from services.models.s_swap import TypeEventSwapAndOut, parse_swap_and_out_event, EventStreamingSwap, StreamingSwap, \
    EventSwap, EventOutbound, EventScheduledOutbound
from services.models.tx import ThorTx, SUCCESS, ThorMetaSwap, ThorTxType, ThorCoin, ThorSubTx


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

        results.sort(key=lambda ev: ev.height)

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

    def find_affiliate(self) -> Tuple[Optional[EventSwap], Optional[EventOutbound]]:
        """
        Affiliate swap properties:
            1) Same asset as input asset (what if its rune?)
            2) streaming_swap_quantity == streaming_swap_count == 1
            3) If streaming: it is in the block with the very first swap

        Affiliate outbound:
            1) Same block as Affiliate Swap event

        In input is Rune => No affiliate outbound

        @return:
        """

    def get_affiliate_fee_and_addr(self) -> Tuple[int, str]:
        in_coin = self.in_coin
        if is_rune_asset(in_coin.asset):
            # In is Rune, so no swap to the affiliate addy
            amount = int(in_coin.amount * self.memo.affiliate_fee)
            return amount, self.memo.affiliate_address
        else:
            # There will be swap + outbound
            ...

    @property
    def in_coin(self):
        return ThorCoin(
            self.attrs.get('in_amount', 0),
            self.attrs.get('in_asset', '')
        )

    @property
    def true_outbounds(self):
        return [
            ev for ev in self.events
            if isinstance(ev, (EventOutbound, EventScheduledOutbound)) and ev.is_outbound or ev.is_refund
        ]

    def build_tx(self) -> ThorTx:
        attrs = self.attrs

        memo_str = self.attrs.get('memo', '')
        height = int(attrs.get('block_height', 0))
        tx_id = attrs.get('id')

        swaps: List[EventSwap] = list(self.find_events(EventSwap))
        pools = []
        liquidity_fee = 0
        slip = 0
        for swap in swaps:
            if swap.pool not in pools:
                pools.append(swap.pool)

            liquidity_fee += swap.liquidity_fee_in_rune
            slip += swap.swap_slip

        in_tx = [
            ThorSubTx(
                address=attrs.get('from_address', ''),
                coins=[
                    ThorCoin(
                        attrs.get('in_amount', 0),
                        attrs.get('in_asset', '')
                    ),
                ],
                tx_id=tx_id
            )
        ]
        out_tx = []  # todo

        affiliate_fee = 0  # todo
        affiliate_address = ''  # todo

        trade_target = 0  # todo
        network_fees = []  # todo

        ss_ev = self.find_event(EventStreamingSwap)
        if ss_ev:
            in_amt, in_asset = ss_ev.asset_amount(is_in=True)
            out_amt, out_asset = ss_ev.asset_amount(is_out=True)
            dep_amt, dep_asset = ss_ev.asset_amount(deposit=True)
            ss_desc = StreamingSwap(
                tx_id=tx_id,
                interval=ss_ev.interval,
                quantity=ss_ev.quantity,
                count=ss_ev.quantity - ss_ev.number_of_failed_swaps,
                last_height=ss_ev.last_height,
                trade_target=ss_ev.swap_target,
                deposit=dep_amt, deposit_asset=dep_asset,
                in_amt=in_amt, in_asset=in_asset,
                out_amt=out_amt, out_asset=out_asset,
                failed_swaps=ss_ev.failed_swap_list,
                failed_swap_reasons=ss_ev.failed_swap_reason_list,
            )
        else:
            ss_desc = StreamingSwap(
                tx_id=tx_id,
                interval=0,
                quantity=1,
                count=1,
                last_height=0,
                trade_target=0,
                deposit=0, deposit_asset='',
                in_amt=0, in_asset='',
                out_amt=0, out_asset='',
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
                streaming=ss_desc
            ),
            status=SUCCESS
        )
        return tx
