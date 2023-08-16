from typing import NamedTuple, List, Optional, Union

from proto.access import DecodedEvent
from services.lib.constants import THOR_BLOCK_TIME
from services.lib.memo import THORMemo


class StreamingSwap(NamedTuple):
    # the hash of a transaction
    tx_id: str

    # how often each swap is made, in blocks
    interval: int

    # the total number of swaps in a streaming swaps
    quantity: int

    # the amount of swap attempts so far
    count: int

    # the block height of the latest swap
    last_height: int

    # the total number of tokens the swapper wants to receive of the output asset
    trade_target: int

    # the number of input tokens the swapper has deposited
    deposit: int

    # the amount of input tokens that have been swapped so far
    in_amt: int

    # the amount of output tokens that have been swapped so far
    out_amt: int

    # the list of swap indexes that failed
    failed_swaps: List[int]

    # the list of reasons that sub-swaps have failed
    failed_swap_reasons: List[str]

    @property
    def progress_on_amount(self):
        """
        Swap progress on input amount in %
        @return: float 0.0...100.0
        """
        return 100.0 * self.in_amt / self.deposit if self.deposit else 0.0

    @property
    def progress_on_swap_count(self):
        """
        Swap progress on swap count in % (count/quantity)
        @return: float 0.0...100.0

        @return:
        """
        return 100.0 * self.count / self.quantity if self.quantity else 0.0

    @classmethod
    def from_json(cls, j):
        return cls(
            j.get('tx_id', ''),
            j.get('interval', 0),
            j.get('quantity', 0),
            j.get('count', 1),
            j.get('last_height', 0),
            j.get('trade_target', 0),
            int(j.get('deposit', 0)),
            int(j.get('in', 0)),
            int(j.get('out', 0)),
            j.get('failed_swaps', []),
            j.get('failed_swap_reasons', []),
        )

    @property
    def blocks_to_wait(self):
        return (self.quantity - self.count) * self.interval

    @property
    def second_to_wait(self):
        return self.blocks_to_wait * THOR_BLOCK_TIME

    @property
    def total_duration(self):
        return self.quantity * self.interval * THOR_BLOCK_TIME


class EventSwapStart(NamedTuple):
    ss: StreamingSwap
    from_address: str
    in_amount: float
    in_asset: str
    out_asset: str
    expected_rate: float
    volume_usd: float
    block_height: int
    memo: THORMemo
    memo_str: str

    @property
    def is_streaming(self):
        return self.ss.quantity > 1

    @property
    def tx_id(self):
        return self.ss.tx_id


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
    original: Optional[DecodedEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: DecodedEvent, height=0):
        attrs = event.attributes
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
            height=height,
        )


class EventStreamingSwap(NamedTuple):
    tx_id: str = ''
    interval: int = 0
    quantity: int = 0
    count: int = 0
    last_height: int = 0
    deposit: str = ''
    in_amt_str: str = ''
    out_out_str: str = ''
    failed_swaps: bytes = b''
    failed_swap_reasons: bytes = b''
    original: Optional[DecodedEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: DecodedEvent, height=0):
        attrs = event.attributes
        return cls(
            tx_id=attrs.get('tx_id', ''),
            interval=int(attrs.get('interval', 0)),
            quantity=int(attrs.get('quantity', 0)),
            count=int(attrs.get('count', 0)),
            last_height=int(attrs.get('last_height', 0)),
            deposit=attrs.get('deposit', ''),
            in_amt_str=attrs.get('in', ''),
            out_out_str=attrs.get('out', ''),
            failed_swaps=attrs.get('failed_swaps', b''),
            failed_swap_reasons=attrs.get('failed_swap_reasons', b''),
            original=event,
            height=height,
        )

    @property
    def is_final(self):
        return self.count == self.quantity


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
    original: Optional[DecodedEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: DecodedEvent, height=0):
        attrs = event.attributes
        return cls(
            tx_id=attrs.get('in_tx_id', ''),
            out_id=attrs.get('id', ''),
            chain=attrs.get('chain', ''),
            from_address=attrs.get('from', ''),
            to_address=attrs.get('to', ''),
            coin=attrs.get('coin', ''),
            amount=int(attrs.get('amount', 0)),
            asset=attrs.get('asset', ''),
            memo=attrs.get('memo', ''),
            original=event,
            height=height,
        )


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
    out_hash: bytes = ''
    module_name: bytes = b''
    max_gas_asset_0: str = ''
    max_gas_amount_0: int = 0
    max_gas_decimals_0: int = 0
    original: Optional[DecodedEvent] = None
    height: int = 0

    @classmethod
    def from_event(cls, event: DecodedEvent, height=0):
        attrs = event.attributes
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
            out_hash=attrs.get('out_hash', b''),
            module_name=attrs.get('module_name', b''),
            max_gas_asset_0=attrs.get('max_gas_asset_0', ''),
            max_gas_amount_0=int(attrs.get('max_gas_amount_0', 0)),
            max_gas_decimals_0=int(attrs.get('max_gas_decimals_0', 0)),
            original=event,
            height=height,
        )


def parse_swap_and_out_event(e: DecodedEvent, height):
    if e.type == 'swap':
        return EventSwap.from_event(e, height)
    elif e.type == 'streaming_swap':
        return EventStreamingSwap.from_event(e, height)
    elif e.type == 'outbound':
        return EventOutbound.from_event(e, height)
    elif e.type == 'scheduled_outbound':
        return EventScheduledOutbound.from_event(e, height)


TypeEventSwapAndOut = Union[EventSwap, EventStreamingSwap, EventOutbound, EventScheduledOutbound]
