import json
from collections import defaultdict
from typing import NamedTuple, List, Optional

from proto.access import DecodedEvent
from services.lib.memo import THORMemo
from services.models.events import TypeEvents, parse_swap_and_out_event, EventOutbound, EventScheduledOutbound
from services.models.tx import ThorCoin, ThorSubTx


class TransactionEvents(NamedTuple):
    attrs: dict
    events: List[TypeEvents]
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
    def status(self):
        return self.attrs.get('status', '')

    @property
    def given_away(self):
        return self.status == self.STATUS_GIVEN_AWAY

    def find_event(self, klass) -> Optional[TypeEvents]:
        return next(self.find_events(klass), None)

    def find_events(self, klass):
        return (e for e in self.events if isinstance(e, klass))

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
