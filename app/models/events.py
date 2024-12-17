from typing import NamedTuple, Optional, Tuple, Union

from lib.constants import POOL_MODULE, NATIVE_RUNE_SYMBOL, thor_to_float, bp_to_float
from lib.utils import expect_string
from jobs.scanner.tx import ThorEvent


class EventSwap(NamedTuple):
    pool: str = ''
    swap_target: int = 0
    swap_slip: int = 0
    liquidity_fee: int = 0
    liquidity_fee_in_rune: int = 0
    emit_asset: str = ''
    streaming_swap_quantity: int = 0
    streaming_swap_count: int = 0
    tx_id: str = ''
    chain: str = ''
    from_address: str = ''
    to_address: str = ''
    coin: str = ''
    amount: int = 0
    asset: str = ''
    memo: str = ''
    original: Optional[ThorEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        return cls(
            pool=attrs.get('pool', ''),
            swap_target=int(attrs.get('swap_target', 0)),
            swap_slip=int(attrs.get('swap_slip', 0)),
            liquidity_fee=int(attrs.get('liquidity_fee', 0)),
            liquidity_fee_in_rune=int(attrs.get('liquidity_fee_in_rune', 0)),
            emit_asset=attrs.get('emit_asset', ''),
            streaming_swap_quantity=int(attrs.get('streaming_swap_quantity', 0)),
            streaming_swap_count=int(attrs.get('streaming_swap_count', 0)),
            tx_id=attrs.get('id', ''),
            chain=attrs.get('chain', ''),
            from_address=attrs.get('from', ''),
            to_address=attrs.get('to', ''),
            coin=attrs.get('coin', ''),
            amount=int(attrs.get('amount', 0)),
            asset=attrs.get('asset', ''),
            memo=attrs.get('memo', ''),
            original=event,
            height=attrs.get('height', 0),
        )


class EventStreamingSwap(NamedTuple):
    tx_id: str = ''
    interval: int = 0
    quantity: int = 0
    count: int = 0
    last_height: int = 0
    deposit: str = ''
    in_amt_str: str = ''
    out_amt_str: str = ''
    failed_swaps: str = ''
    failed_swap_reasons: str = ''
    original: Optional[ThorEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        return cls(
            tx_id=attrs.get('tx_id', ''),
            interval=int(attrs.get('interval', 0)),
            quantity=int(attrs.get('quantity', 0)),
            count=int(attrs.get('count', 0)),
            last_height=int(attrs.get('last_height', 0)),
            deposit=attrs.get('deposit', ''),
            in_amt_str=attrs.get('in', ''),
            out_amt_str=attrs.get('out', ''),
            failed_swaps=expect_string(attrs.get('failed_swaps', b'')),
            failed_swap_reasons=expect_string(attrs.get('failed_swap_reasons', b'')),
            original=event,
            height=attrs.get('height', 0),
        )

    @property
    def is_final(self):
        return self.count == self.quantity

    @property
    def failed_swap_list(self):
        return list(filter(bool, self.failed_swaps.split(',')))

    @property
    def number_of_failed_swaps(self):
        return len(self.failed_swap_list)

    @property
    def failed_swap_reason_list(self):
        return list(filter(bool, self.failed_swap_reasons.split('\n')))

    def asset_amount(self, is_in=False, is_out=False, deposit=False):
        if deposit:
            s = self.deposit
        elif is_in:
            s = self.in_amt_str
        elif is_out:
            s = self.out_amt_str
        else:
            raise ValueError()

        amount, asset = s.split(' ')
        return int(amount), asset.strip()


class EventOutbound(NamedTuple):
    tx_id: str = ''  # in_tx_id
    out_id: str = ''
    chain: str = ''
    from_address: str = ''
    to_address: str = ''
    coin: str = ''
    amount: int = 0
    asset: str = ''
    memo: str = ''
    original: Optional[ThorEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        return cls(
            tx_id=attrs.get('in_tx_id', ''),
            out_id=attrs.get('id', ''),
            chain=attrs.get('chain', ''),
            from_address=attrs.get('from', ''),
            to_address=attrs.get('to', ''),
            coin=attrs.get('coin', ''),
            amount=int(attrs.get('amount', 0) or attrs.get('_amount', 0)),
            asset=attrs.get('asset', '') or attrs.get('_asset', ''),
            memo=attrs.get('memo', ''),
            original=event,
            height=attrs.get('height', 0),
        )

    @property
    def is_refund_memo(self):
        return self.memo.upper().startswith('REFUND:')

    @property
    def is_outbound_memo(self):
        return self.memo.upper().startswith('OUT:')

    @property
    def is_affiliate(self):
        return self.from_address == POOL_MODULE and self.chain == 'THOR' and self.asset == NATIVE_RUNE_SYMBOL

    @property
    def amount_asset(self) -> Tuple[int, str]:
        return self.amount, self.asset


class EventScheduledOutbound(NamedTuple):
    chain: str = ''
    to_address: str = ''
    vault_pub_key: str = ''
    coin_asset: str = ''
    coin_amount: int = 0
    coin_decimals: int = 0
    memo: str = ''
    gas_rate: int = 0
    tx_id: str = ''  # in_hash
    out_hash: str = ''
    module_name: str = ''
    max_gas_asset_0: str = ''
    max_gas_amount_0: int = 0
    max_gas_decimals_0: int = 0
    original: Optional[ThorEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        return cls(
            chain=attrs.get('chain', ''),
            to_address=attrs.get('to_address', ''),
            vault_pub_key=attrs.get('vault_pub_key', ''),
            coin_asset=attrs.get('coin_asset', ''),
            coin_amount=int(attrs.get('coin_amount', 0)),
            coin_decimals=int(attrs.get('coin_decimals', 0)),
            memo=attrs.get('memo', ''),
            gas_rate=int(attrs.get('gas_rate', 0)),
            tx_id=attrs.get('in_hash', ''),
            out_hash=expect_string(attrs.get('out_hash', b'')),
            module_name=expect_string(attrs.get('module_name', b'')),
            max_gas_asset_0=attrs.get('max_gas_asset_0', ''),
            max_gas_amount_0=int(attrs.get('max_gas_amount_0', 0)),
            max_gas_decimals_0=int(attrs.get('max_gas_decimals_0', 0)),
            original=event,
            height=attrs.get('height', 0),
        )

    @property
    def is_refund_memo(self):
        return self.memo.upper().startswith('REFUND:')

    @property
    def is_outbound_memo(self):
        return self.memo.upper().startswith('OUT:')

    @property
    def amount_asset(self) -> Tuple[int, str]:
        return self.coin_amount, self.coin_asset


class EventLoanOpen(NamedTuple):
    tx_id: str
    collateral_deposited: int
    debt_issued: int
    collateralization_ratio: float
    collateral_asset: str
    target_asset: str
    owner: str
    height: int = 0

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        cr = bp_to_float(attrs.get('collateralization_ratio', 0))
        return cls(
            tx_id='',
            collateral_deposited=int(attrs.get('collateral_deposited', 0)),
            debt_issued=int(attrs.get('debt_issued', 0)),
            collateralization_ratio=cr,
            collateral_asset=attrs.get('collateral_asset', ''),
            target_asset=attrs.get('target_asset', ''),
            owner=attrs.get('owner', ''),
            height=event.height  # fixme!!

        )

    @property
    def debt_usd(self):
        return thor_to_float(self.debt_issued)

    @property
    def collateral_float(self):
        return thor_to_float(self.collateral_deposited)


class EventLoanRepayment(NamedTuple):
    tx_id: str
    collateral_withdrawn: int
    debt_repaid: int
    collateral_asset: str
    owner: str
    height: int = 0

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        return cls(
            tx_id='',
            collateral_withdrawn=int(attrs.get('collateral_withdrawn', 0)),
            debt_repaid=int(attrs.get('debt_repaid', 0)),
            collateral_asset=attrs.get('collateral_asset', ''),
            owner=attrs.get('owner', ''),
            height=event.height
        )

    @property
    def debt_repaid_usd(self):
        return thor_to_float(self.debt_repaid)

    @property
    def collateral_float(self):
        return thor_to_float(self.collateral_withdrawn)


class EventTradeAccountDeposit(NamedTuple):
    tx_id: str
    amount: int
    asset: str
    rune_address: str
    asset_address: str
    height: int = 0
    original: Optional[ThorEvent] = None

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        return cls(
            tx_id=attrs.get('tx_id', ''),
            amount=int(attrs.get('amount', 0)),
            asset=attrs.get('asset', ''),
            rune_address=attrs.get('rune_address', ''),
            asset_address=attrs.get('asset_address', ''),
            height=event.height,
            original=event
        )

    @property
    def amount_float(self):
        return thor_to_float(self.amount)


class EventTradeAccountWithdraw(NamedTuple):
    tx_id: str
    amount: int
    asset: str
    rune_address: str
    asset_address: str
    height: int = 0
    original: Optional[ThorEvent] = None

    @classmethod
    def from_event(cls, event: ThorEvent):
        attrs = event.attrs
        return cls(
            tx_id=attrs.get('tx_id', ''),
            amount=int(attrs.get('amount', 0)),
            asset=attrs.get('asset', ''),
            rune_address=attrs.get('rune_address', ''),
            asset_address=attrs.get('asset_address', ''),
            height=event.height,
            original=event
        )

    @property
    def amount_float(self):
        return thor_to_float(self.amount)


def parse_swap_and_out_event(e: ThorEvent):
    if e.type == 'swap':
        return EventSwap.from_event(e)
    elif e.type == 'streaming_swap':
        return EventStreamingSwap.from_event(e)
    elif e.type == 'outbound':
        return EventOutbound.from_event(e)
    elif e.type == 'scheduled_outbound':
        return EventScheduledOutbound.from_event(e)
    elif e.type == 'loan_open':
        return EventLoanOpen.from_event(e)
    elif e.type == 'loan_repayment':
        return EventLoanRepayment.from_event(e)
    elif e.type == 'trade_account_deposit':
        return EventTradeAccountDeposit.from_event(e)
    elif e.type == 'trade_account_withdraw':
        return EventTradeAccountWithdraw.from_event(e)


TypeEventSwapAndOut = Union[EventSwap, EventStreamingSwap, EventOutbound, EventScheduledOutbound]
TypeEvents = Union[
    EventSwap,
    EventStreamingSwap,
    EventOutbound,
    EventScheduledOutbound,
    EventLoanOpen,
    EventLoanRepayment,
    EventTradeAccountDeposit,
    EventTradeAccountWithdraw,
]
