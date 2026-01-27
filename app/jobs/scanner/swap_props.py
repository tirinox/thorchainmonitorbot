import json
from collections import defaultdict
from typing import NamedTuple, List, Optional

from jobs.scanner.block_result import ThorEvent
from models.asset import is_rune, is_trade_asset, Asset
from models.events import EventSwap, EventStreamingSwap, EventOutbound, parse_swap_and_out_event, TypeEventSwapAndOut, \
    EventTradeAccountDeposit
from models.memo import ActionType
from models.memo import THORMemo
from models.s_swap import StreamingSwap
from models.tx import ThorAction, SUCCESS, ThorMetaSwap, ThorCoin, ThorSubTx


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
        for key, str_cont in attrs.items():
            if key.startswith("ev_"):
                raw_dict = json.loads(str_cont)
                event = ThorEvent.from_dict(raw_dict)
                swap_ev = parse_swap_and_out_event(event)
                results.append(swap_ev)

        results.sort(key=lambda ev: ev.height)

        return cls(
            attrs,
            results,
            memo=THORMemo.parse_memo(attrs.get('memo', ''), no_raise=True)
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
        # todo: new algorithm for detecting finished swaps

        if self.is_output_l1_asset:
            # if output is L1 asset, we wait to outbound
            out_asset = self.attrs.get('out_asset').upper()
            if any(isinstance(ev, EventOutbound) and ev.asset.upper() == out_asset for ev in self.events):
                return True
        else:
            # if there is any outbound to my address, except internal outbounds (in the middle of double swap)
            if any((isinstance(ev, EventOutbound) and ev.to_address == self.from_address) for ev in self.true_outbounds):
                return True

            # if there is any streaming swap event, it's done
            if any(isinstance(ev, EventStreamingSwap) for ev in self.events):
                return True

            # if it contains a deposit of trade asset, it's done
            if any(isinstance(ev, EventTradeAccountDeposit) and ev.rune_address for ev in self.events):
                return True

        return False

    @property
    def in_coin(self):
        return ThorCoin(
            int(self.attrs.get('in_amount', 0)),
            self.attrs.get('in_asset', '')
        )

    @property
    def from_address(self):
        return self.attrs.get('from_address', '')

    @property
    def has_started(self):
        return bool(self.memo and self.from_address)

    @property
    def is_completed(self):
        return self.has_started and self.has_swaps and self.is_finished

    @property
    def true_outbounds(self):
        outbounds = [
            ev for ev in self.events
            if isinstance(ev, EventOutbound) and (ev.is_outbound_memo or ev.is_refund_memo)
        ]

        return outbounds

    def gather_outbounds(self) -> List[ThorSubTx]:
        outbounds = self.true_outbounds
        if not outbounds:
            return []

        all_are_rune = all(is_rune(ev.amount_asset[1]) for ev in outbounds)
        if all_are_rune:
            max_amount = max(int(ev.amount_asset[0]) for ev in outbounds)
        else:
            max_amount = 0

        pre_results = []
        for outbound in outbounds:
            amount, asset = outbound.amount_asset
            coins = [ThorCoin(amount, asset)]

            if all_are_rune:
                is_affiliate = int(amount) != max_amount
            elif is_rune(asset):
                is_affiliate = True
            else:
                is_affiliate = False

            pre_results.append(ThorSubTx(
                outbound.to_address, coins, outbound.tx_id,
                height=outbound.height,
                is_affiliate=is_affiliate
            ))

        results_by_recipient = defaultdict(list)
        for result in pre_results:
            results_by_recipient[f'{result.address}-{result.tx_id}'].append(result)

        results = []
        for out_list in results_by_recipient.values():
            coins = {}
            for out_item in out_list:
                for coin in out_item.coins:
                    if coin.asset not in coins:
                        coins[coin.asset] = 0
                    coins[coin.asset] += coin.amount

            tx_id = out_list[0].tx_id  # same for all
            address = out_list[0].address  # same for all
            height = max(ev.height for ev in out_list)
            is_affiliate = any(ev.is_affiliate for ev in out_list)
            is_refund = any(asset == self.in_coin.asset for asset in coins)
            results.append(ThorSubTx(
                address,
                coins=[ThorCoin(amount, asset) for asset, amount in coins.items()],
                tx_id=tx_id,
                height=height,
                is_affiliate=is_affiliate,
                is_refund=is_refund
            ))

        return results

    @property
    def has_swaps(self):
        return any(isinstance(ev, EventSwap) for ev in self.events)

    @property
    def is_output_trade(self):
        return is_trade_asset(self.attrs.get('out_asset', ''))

    @property
    def is_output_l1_asset(self):
        asset = Asset.from_string(self.attrs.get('out_asset', ''))
        return not asset.is_trade and not asset.is_synth and not asset.is_virtual and not asset.is_secured

    def build_action(self, ts: int) -> ThorAction:
        attrs = self.attrs

        memo_str = self.attrs.get('memo', '')
        height = int(attrs.get('block_height', 0))  # when it was observed for the first time
        tx_id = attrs.get('id')

        swaps: List[EventSwap] = list(self.find_events(EventSwap))
        pools = []
        liquidity_fee = 0
        slip = 0
        for swap in swaps:
            if swap.pool not in pools:
                pools.append(swap.pool)

            liquidity_fee += swap.liquidity_fee_in_rune
            slip = max(slip, swap.swap_slip)

        in_tx = [
            ThorSubTx(
                address=attrs.get('from_address', ''),
                coins=[self.in_coin],
                tx_id=tx_id,
                height=height,
            )
        ]

        out_txs = self.gather_outbounds()

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
                deposit=dep_amt,
                in_amt=in_amt, source_asset=dep_asset,
                out_amt=out_amt, target_asset=out_asset,
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
                deposit=0, source_asset='',
                in_amt=0,
                out_amt=0, target_asset='',
                failed_swaps=[],
                failed_swap_reasons=[]
            )

        network_fees = []  # ignore so far, not really used

        tx = ThorAction(
            date_timestamp=int(ts),
            height=height,
            type=ActionType.SWAP.value,
            pools=pools,
            in_tx=in_tx,
            out_tx=out_txs,
            meta_swap=ThorMetaSwap(
                liquidity_fee=liquidity_fee,
                network_fees=network_fees,
                trade_slip=slip,
                trade_target=trade_target,
                memo=memo_str,
                affiliate_fee=self.memo.affiliate_fee_0_1,
                affiliate_address=self.memo.affiliate_address,
                streaming=ss_desc
            ),
            status=SUCCESS
        )
        return tx
