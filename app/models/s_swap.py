from dataclasses import dataclass
from typing import NamedTuple, List, Optional

from pydantic import ConfigDict, BaseModel, Field

from api.aionode.types import ThorSwapperClout
from lib.constants import THOR_BLOCK_TIME, thor_to_float
from .memo import THORMemo


def is_streaming_swap(interval: Optional[int], quantity: Optional[int], adv_swap_queue: bool) -> bool:
    """
    interval and quantity are the memo's LIM/INTERVAL/QUANTITY; the parser gives 0/1 when they are omitted,
    so "no parameters" and an explicit /0/1 look the same, and both are one sub-swap.
    With the Advanced Swap Queue (Mimir EnableAdvSwapQueue) a swap streams unless the memo asks for exactly one
    sub-swap (quantity 0 lets the protocol choose, interval 0 streams rapidly). With the classic queue it also
    needs an interval. On 259 real mainnet swaps this agrees with Midgard's isStreamingSwap in every case.
    """
    interval = interval or 0
    quantity = 1 if quantity is None else quantity
    if quantity == 1:
        return False
    return adv_swap_queue or interval > 0


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
    # THORChain block height where the swap start was observed by this bot.
    block_height: int
    memo: THORMemo
    memo_str: str
    clout: Optional[ThorSwapperClout] = None
    quote: Optional[dict] = None
    quantity: Optional[int] = 1
    interval: Optional[int] = 1
    is_limit: Optional[bool] = False
    adv_swap_queue: bool = True  # Mimir EnableAdvSwapQueue when the swap was seen

    @property
    def in_amount_float(self) -> float:
        return thor_to_float(self.in_amount)

    @property
    def is_streaming(self):
        return is_streaming_swap(self.interval, self.quantity, self.adv_swap_queue)

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


class RapidSwapStats(NamedTuple):
    """
    Statistics about rapid (batched) swap execution within a single streaming swap.

    Example – ev_swap rows in one block with streaming counts [60, 60, 61, 61]
      total_swaps          = 2  (logical executions: 60 and 61)
      distinct_blocks      = 1
      blocks_with_multi    = 1
      blocks_saved         = 2 - 1 = 1
    """
    total_swaps: int           # total number of logical swap executions (distinct streaming_swap_count values)
    distinct_blocks: int       # number of unique block heights containing those logical executions
    blocks_with_multi: int     # blocks that hold more than one logical execution (rapid swap active)
    blocks_saved: int          # total_swaps - distinct_blocks  (execution blocks saved)
    streaming_swap_quantity: int = 0  # first non-zero streaming_swap_quantity across all ev_swap events

    @property
    def saved_time(self) -> float:
        """Wall-clock seconds saved by rapid swap batching (blocks_saved × THOR_BLOCK_TIME)."""
        return self.blocks_saved * THOR_BLOCK_TIME

