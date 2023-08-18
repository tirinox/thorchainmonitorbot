import json
from collections import defaultdict
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
            Usage:
            foo = await self.read_tx_status(swap_ev.tx_id)
            foo_ev = self.restore_events_from_tx_status(foo)
        """
        if not attrs:
            return

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
    def is_finished(self) -> bool:
        # unequivocally, it's done if there is any EventScheduledOutbound
        if any(isinstance(ev, EventScheduledOutbound) for ev in self.events):
            return True

        # if there is any outbound to my address, except internal outbounds (in the middle of double swap)
        if any((isinstance(ev, EventOutbound) and ev.to_address == self.inbound_address)
               for ev in self.true_outbounds):
            return True

        return False

    def get_affiliate_fee_and_addr(self) -> Tuple[int, str]:
        if self.memo.affiliate_fee and self.memo.affiliate_address:
            in_coin = self.in_coin
            if is_rune_asset(in_coin.asset):
                # In is Rune, so no swap to the affiliate addy
                amount = int(in_coin.amount * self.memo.affiliate_fee)
                return amount, self.memo.affiliate_address
            else:
                for ev in self.events:
                    if isinstance(ev, EventOutbound) and ev.to_address != self.inbound_address and ev.is_outbound:
                        return ev.amount, ev.to_address

        return 0, ''  # otherwise not found

    @property
    def in_coin(self):
        return ThorCoin(
            int(self.attrs.get('in_amount', 0)),
            self.attrs.get('in_asset', '')
        )

    @property
    def inbound_address(self):
        return self.attrs.get('from_address', '')

    @property
    def has_started(self):
        return self.memo and self.inbound_address

    @property
    def true_outbounds(self):
        return [
            ev for ev in self.events
            if isinstance(ev, (EventOutbound, EventScheduledOutbound)) and (ev.is_outbound or ev.is_refund)
        ]

    def gather_outbound(self) -> List[ThorSubTx]:
        results = defaultdict(list)
        # in_address = self.inbound_address
        for outbound in self.true_outbounds:
            # here we must separate the affiliate outbound.

            results[outbound.to_address].append(ThorCoin(*outbound.amount_asset))

        return [ThorSubTx(address, coins, '') for address, coins in results.items()]

    @property
    def has_swaps(self):
        return any(isinstance(ev, EventSwap) for ev in self.events)

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
                coins=[self.in_coin],
                tx_id=tx_id
            )
        ]
        out_tx = self.gather_outbound()

        _affiliate_fee_paid, affiliate_address = self.get_affiliate_fee_and_addr()

        trade_target = 0  # ignore so far, not really used

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
                trade_target=trade_target,
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

        network_fees = []  # ignore so far, not really used

        timestamp = int(datetime.now().timestamp() * 1e9)

        tx = ThorTx(
            date=timestamp,
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
                affiliate_fee=self.memo.affiliate_fee,  # (0..1)
                memo=memo_str,
                affiliate_address=affiliate_address,
                streaming=ss_desc
            ),
            status=SUCCESS
        )
        return tx
