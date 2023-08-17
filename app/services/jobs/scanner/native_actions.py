import datetime
import sys
from collections import defaultdict
from typing import List

from aioredis import Redis

from services.jobs.affiliate_merge import ZERO_HASH
from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.native_scan import BlockResult
from services.jobs.scanner.swap_start_detector import SwapStartDetector
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger, say, hash_of_string_repr
from services.models.s_swap import parse_swap_and_out_event, StreamingSwap, EventSwapStart, EventOutbound, \
    EventScheduledOutbound, TypeEventSwapAndOut, EventSwap
from services.models.tx import ThorTx, ThorTxType, ThorMetaSwap, SUCCESS


class NativeActionExtractor(WithDelegates, INotified, WithLogger):
    STATUS_OBSERVED_IN = 'observed_in'
    STATUS_WAITING_FOR_OUTBOUND = 'wait4out'
    STATUS_FINISHED = 'finished'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._swap_detector = SwapStartDetector(deps)
        self._db = EventDatabase(deps.db)

        self.dbg_watch_swap_id = None
        self.dbg_start_observed = False
        self.dbg_start_time = datetime.datetime.now()
        self.dbg_swaps = 0
        self.dbg_file = None

    async def on_data(self, sender, block: BlockResult) -> List[ThorTx]:
        new_swaps = self._swap_detector.detect_swaps(block)

        # Incoming swap intentions will be recorded in the DB
        await self.register_new_swaps(new_swaps, block.block_no)

        # Swaps and Outs
        interesting_events = list(self.get_events_of_interest(block))

        # To calculate progress and final slip/fees
        await self.register_swap_events(block, interesting_events)

        return await self.detect_swap_finished(block, interesting_events)

    async def register_new_swaps(self, swaps: List[EventSwapStart], height):
        self.logger.info(f"New swaps {len(swaps)} in block #{height}")

        for swap in swaps:
            props = await self._db.read_tx_status(swap.tx_id)
            if not props or not props.attrs.get('status'):
                # self.logger.debug(f'Detect new swap: {swap.tx_id} from {swap.from_address} ({swap.memo})')
                await self._db.write_tx_status_kw(
                    swap.tx_id,
                    id=swap.tx_id,
                    status=self.STATUS_OBSERVED_IN,
                    memo=swap.memo_str,
                    from_address=swap.from_address,
                    in_amount=swap.in_amount,
                    in_asset=swap.in_asset,
                    is_streaming=swap.is_streaming,
                    out_asset=swap.out_asset,
                    block_height=swap.block_height,
                    volume_usd=swap.volume_usd,
                )

            # debugging stuff
            if swap.tx_id == self.dbg_watch_swap_id and not self.dbg_start_observed:
                self.dbg_print(f'👿 Start watching swap\n')
                self.dbg_print(swap, '\n\n')

                await say('Found a swap')

                self.dbg_start_observed = True

    def is_affiliate_swap(self, ev: EventSwap, tx_props: dict):
        return ev.streaming_swap_count == ev.streaming_swap_quantity == 1

    @staticmethod
    def expect_scheduled_outbound(tx_props: dict):
        ...

    @staticmethod
    def suspect_outbound_internal(ev: EventOutbound):
        return ev.out_id == ZERO_HASH and ev.chain == 'THOR'

    async def register_swap_events(self, block: BlockResult, interesting_events: List[TypeEventSwapAndOut]):
        r: Redis = await self.deps.db.get_redis()

        boom = False
        for swap_ev in interesting_events:
            hash_key = hash_of_string_repr(swap_ev)

            print(f'Write {swap_ev.tx_id} => {hash_key}')
            print(swap_ev)

            await self._db.write_tx_status(swap_ev.tx_id, {
                f"ev_{hash_key}": swap_ev.original.to_dict
            })

            # --8<-- debugging stuff --8<--
            if isinstance(swap_ev, EventSwap):
                self.dbg_swaps += 1
            if swap_ev.tx_id == self.dbg_watch_swap_id:
                self.dbg_print(f'👹 new event for watched TX!!! {swap_ev.__class__} at block #{swap_ev.height}\n')
                self.dbg_print(swap_ev)
                self.dbg_print('----------\n')

                if not boom:
                    await say('Event!!')
                    boom = True

                if isinstance(swap_ev, EventScheduledOutbound):
                    await say('Scheduled outbound!')
            # --8<-- debugging stuff --8<--

    @staticmethod
    def get_events_of_interest(block: BlockResult) -> List[TypeEventSwapAndOut]:
        for ev in block.end_block_events:
            swap_ev = parse_swap_and_out_event(ev)
            if swap_ev:
                yield swap_ev

    async def detect_swap_finished(self,
                                   block: BlockResult,
                                   interesting_events: List[TypeEventSwapAndOut]) -> List[ThorTx]:
        """
            We do not wait until scheduled outbound will be sent out.
            Swap end is detected by
                a) EventScheduledOutbound
                b) EventOutbound for Rune/synths
        """
        group_by_in = defaultdict(list)

        for ev in interesting_events:
            if isinstance(ev, (EventOutbound, EventScheduledOutbound)):
                group_by_in[ev.tx_id].append(ev)

        results = []
        for tx_id, group in group_by_in.items():
            results += await self._handle_finishing_swap_events_for_tx(tx_id, block.block_no, group)

        # --8<-- debugging stuff --8<--
        # for tx_id, events in group_by_in.items():
        #     print(f"TX finish {tx_id} => {[e.__class__.__name__ for e in events]}")

        # print(f'-----! SWAP SPEED is {self.dbg_swap_speed:.2f} swaps/sec')
        # --8<-- debugging stuff --8<--

        return []

    async def _handle_finishing_swap_events_for_tx(self, tx_id: str, block_no, group: List[TypeEventSwapAndOut]):
        # Swap is finished when
        #   Is it a streaming swap?
        #       a) After ss_count == ss_quantity > 1  => outbound_detected OR scheduled_outbound
        #       b)

        # Build ThorTx
        tx = ThorTx(
            date=int(datetime.datetime.utcnow().timestamp() * 1e9),
            height=block_no,
            type=ThorTxType.TYPE_SWAP,
            pools=[],
            in_tx=[],
            out_tx=[],
            meta_swap=ThorMetaSwap(
                liquidity_fee='0',
                network_fees=[],
                trade_slip='0',
                trade_target='0',
                affiliate_fee=0.0,
                memo='',
                affiliate_address='',
                streaming=StreamingSwap(
                    tx_id='',
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
            ),
            status=SUCCESS
        )

        return []

    # --- debug and research ---

    def dbg_open_file(self, filename):
        self.dbg_file = open(filename, 'w')

    def __del__(self):
        if self.dbg_file:
            self.dbg_file.close()

    def dbg_reset_swap_speed_counter(self):
        self.dbg_start_time = datetime.datetime.now()
        self.dbg_swaps = 0

    @property
    def dbg_swap_speed(self):
        elapsed_sec = (datetime.datetime.now() - self.dbg_start_time).total_seconds()
        return self.dbg_swaps / elapsed_sec if elapsed_sec else 0.0

    def dbg_print(self, *args):
        s = self.dbg_file or sys.stdout
        print(*args, file=s)
