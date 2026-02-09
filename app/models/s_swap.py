from dataclasses import dataclass
from typing import NamedTuple, List, Optional

from pydantic import ConfigDict, BaseModel, Field

from api.aionode.types import ThorSwapperClout
from lib.constants import THOR_BLOCK_TIME, thor_to_float
from .memo import THORMemo


class StreamingSwap(BaseModel):
    """
    Pydantic v2 replacement for your NamedTuple.
    """

    model_config = ConfigDict(
        populate_by_name=True,  # allow passing either field names or aliases
        frozen=True,  # immutable like NamedTuple
        extra="ignore",  # ignore unknown keys in incoming JSON
    )

    # the hash of a transaction
    tx_id: str = ""

    # how often each swap is made, in blocks
    interval: int = 0

    # the total number of swaps in a streaming swaps
    quantity: int = 0

    # the amount of swap attempts so far
    count: int = 1

    # the block height of the latest swap
    last_height: int = 0

    # the total number of tokens the swapper wants to receive of the output asset
    trade_target: int = 0

    # the number of input tokens the swapper has deposited
    deposit: int = 0

    # the amount of input tokens that have been swapped so far
    in_amt: int = Field(default=0, alias="in")
    source_asset: str = ""

    # the amount of output tokens that have been swapped so far
    out_amt: int = Field(default=0, alias="out")
    target_asset: str = ""

    destination: str = ""

    # the list of swap indexes that failed
    failed_swaps: List[int] = Field(default_factory=list)

    # the list of reasons that sub-swaps have failed
    failed_swap_reasons: List[str] = Field(default_factory=list)

    @property
    def progress_on_amount(self) -> float:
        """Swap progress on input amount in % (0.0..100.0)."""
        return 100.0 * self.in_amt / self.deposit if self.deposit else 0.0

    @property
    def progress_on_swap_count(self) -> float:
        """Swap progress on swap count in % (count/quantity) (0.0..100.0)."""
        return 100.0 * self.count / self.quantity if self.quantity else 0.0

    @property
    def blocks_to_wait(self) -> int:
        return (self.quantity - self.count) * self.interval

    @property
    def second_to_wait(self) -> float:
        return self.blocks_to_wait * THOR_BLOCK_TIME

    @property
    def total_duration(self) -> float:
        return self.quantity * self.interval * THOR_BLOCK_TIME

    @property
    def successful_swaps(self) -> int:
        return self.quantity - len(self.failed_swaps)

    @property
    def success_rate(self) -> float:
        return (self.successful_swaps / self.quantity) if self.quantity else 1.0


@dataclass
class AlertSwapStart:
    tx_id: str
    from_address: str
    destination_address: str
    in_amount: int
    in_asset: str
    out_asset: str
    volume_usd: float
    block_height: int
    memo: THORMemo
    memo_str: str
    clout: Optional[ThorSwapperClout] = None
    quote: Optional[dict] = None
    quantity: Optional[int] = 1
    interval: Optional[int] = 1
    is_limit: Optional[bool] = False

    @property
    def in_amount_float(self) -> float:
        return thor_to_float(self.in_amount)

    @property
    def is_streaming(self):
        # fixme: unreliable check? maybe interval is detected automatically?
        # !!!!
        # with advanced queue, every swap is streaming if not quantity=1 and interval=1
        return not (self.quantity == 1 and self.interval == 1)

    @property
    def expected_out_amount(self):
        return self.quote.get('expected_amount_out', 0) if self.quote else 0

    @property
    def expected_total_swap_sec(self):
        return self.quote.get('total_swap_seconds',
                              0) if self.quote else self.interval * self.quantity * THOR_BLOCK_TIME

    @property
    def expected_outbound_delay_sec(self):
        return self.quote.get('outbound_delay_seconds', 0) if self.quote else 0


class EventChangedStreamingSwapList(NamedTuple):
    new_swaps: List[StreamingSwap]
    completed_swaps: List[StreamingSwap]

    @classmethod
    def empty(cls):
        return cls(new_swaps=[], completed_swaps=[])
