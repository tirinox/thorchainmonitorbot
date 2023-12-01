import json
from collections import defaultdict
from datetime import datetime
from typing import NamedTuple, List, Optional, Tuple

from proto.access import DecodedEvent
from services.lib.memo import THORMemo
from services.lib.money import is_rune
from services.models.events import EventSwap, EventStreamingSwap, EventOutbound, EventScheduledOutbound, \
    parse_swap_and_out_event, TypeEventSwapAndOut
from services.models.price import LastPriceHolder
from services.models.s_swap import StreamingSwap
from services.models.tx import ThorTx, SUCCESS, ThorMetaSwap, ThorCoin, ThorSubTx
from services.models.tx_type import TxType


class SwapProps(NamedTuple):
    attrs: dict
    events: List[TypeEventSwapAndOut]
    memo: THORMemo

    STATUS_OBSERVED_IN = 'observed_in'
    STATUS_GIVEN_AWAY = 'given_away'

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

    @property
    def status(self):
        return self.attrs.get('status', '')

    @property
    def given_away(self):
        return self.status == self.STATUS_GIVEN_AWAY

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
        if any((isinstance(ev, EventOutbound) and ev.to_address == self.inbound_address) for ev in self.true_outbounds):
            return True

        # if there is any streaming swap event, it's done
        if any(isinstance(ev, EventStreamingSwap) for ev in self.events):
            return True

        return False

    def get_affiliate_fee_and_addr(self) -> Tuple[int, str]:
        if self.memo.affiliate_fee and self.memo.affiliate_address:
            in_coin = self.in_coin
            if is_rune(in_coin.asset):
                # In is Rune, so no swap to the affiliate addy
                amount = int(in_coin.amount * self.memo.affiliate_fee)
                return amount, self.memo.affiliate_address
            else:
                for ev in self.events:
                    # fixme: possible bug. it dest addy is THORName,
                    #  it will mismatch anyway because events have natural addresses
                    if (isinstance(ev, EventOutbound)
                            and ev.to_address != self.memo.dest_address
                            and ev.is_outbound_memo):
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
        return bool(self.memo and self.inbound_address)

    @property
    def true_outbounds(self):
        return [
            ev for ev in self.events
            if isinstance(ev, (EventOutbound, EventScheduledOutbound)) and (ev.is_outbound_memo or ev.is_refund_memo)
        ]

    def gather_outbound(self, affiliate_address) -> List[ThorSubTx]:
        results = defaultdict(list)
        # in_address = self.inbound_address
        for outbound in self.true_outbounds:
            # here we must separate the affiliate outbound.
            if outbound.to_address == affiliate_address:
                continue

            results[outbound.to_address].append(ThorCoin(*outbound.amount_asset))

        return [ThorSubTx(address, coins, '') for address, coins in results.items()]

    def find_outbound(self, address) -> Optional[ThorCoin]:
        for outbound in self.true_outbounds:
            if outbound.to_address == address:
                return ThorCoin(*outbound.amount_asset)

    @property
    def has_swaps(self):
        return any(isinstance(ev, EventSwap) for ev in self.events)

    @staticmethod
    def _calculate_output_usd_volume(out_txs: List[ThorSubTx], pools: LastPriceHolder) -> Optional[float]:
        out_usd = 0.0
        for sub_tx in out_txs:
            for coin in sub_tx.coins:
                usd_value = pools.convert_to_usd(coin.amount_float, coin.asset)
                if usd_value is None:
                    return
                out_usd += usd_value

        return out_usd

    def build_tx(self, price_holder: Optional[LastPriceHolder]) -> ThorTx:
        attrs = self.attrs

        memo_str = attrs.get('memo', '')
        height = int(attrs.get('block_height', 0))
        tx_id = attrs.get('id')

        swaps: List[EventSwap] = list(self.find_events(EventSwap))
        pools = []
        liquidity_fee = 0
        slip = 0
        for swap in swaps:
            if swap.pool not in pools:
                pools.append(swap.pool)

            # todo: too low slip fee
            # fixme: (!) work here
            liquidity_fee += swap.liquidity_fee_in_rune
            slip = max(slip, swap.swap_slip)

        in_tx = [
            ThorSubTx(
                address=attrs.get('from_address', ''),
                coins=[self.in_coin],
                tx_id=tx_id
            )
        ]

        _affiliate_fee_paid, affiliate_address = self.get_affiliate_fee_and_addr()

        out_tx = self.gather_outbound(affiliate_address)

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

        input_usd_volume = attrs.get('volume_usd', 0.0)
        output_usd_volume = self._calculate_output_usd_volume(out_tx, price_holder) if price_holder else None
        affiliate_factor = self.memo.affiliate_fee
        real_slip_usd = input_usd_volume - output_usd_volume - (input_usd_volume * affiliate_factor)
        # slip = max(real_slip_usd, slip)
        print(f"{tx_id =} ; {real_slip_usd = } ; block's {slip = }")

        network_fees = []  # ignore so far, not really used

        timestamp = int(datetime.now().timestamp() * 1e9)

        tx = ThorTx(
            date=timestamp,
            height=height,
            type=TxType.SWAP,
            pools=pools,
            in_tx=in_tx,
            out_tx=out_tx,
            meta_swap=ThorMetaSwap(
                liquidity_fee=liquidity_fee,
                network_fees=network_fees,
                trade_slip=slip,
                trade_target=trade_target,
                affiliate_fee=affiliate_factor,  # (0..1)
                memo=memo_str,
                affiliate_address=affiliate_address,
                streaming=ss_desc
            ),
            status=SUCCESS
        )
        return tx
