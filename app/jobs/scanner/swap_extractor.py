import datetime
import os
import sys
from collections import defaultdict
from typing import List, Optional

from jobs.scanner.event_db import EventDatabase
from jobs.scanner.native_scan import BlockResult
from jobs.scanner.swap_props import SwapProps
from jobs.scanner.swap_start_detector import SwapStartDetector
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger, hash_of_string_repr, say
from models.events import EventOutbound, EventScheduledOutbound, \
    parse_swap_and_out_event, TypeEventSwapAndOut, EventTradeAccountDeposit, EventSwap
from models.tx import ThorAction


class SwapExtractorBlock(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._swap_detector = SwapStartDetector(deps)

        expiration_sec = deps.cfg.as_interval('native_scanner.db.ttl', '3d')
        self._db = EventDatabase(deps.db, expiration_sec=expiration_sec)

        self.dbg_watch_swap_id = None
        self.dbg_start_observed = False
        self.dbg_start_time = datetime.datetime.now()
        self.dbg_swaps = 0
        self.dbg_file = None
        self.dbg_ignore_finished_status = False

    async def on_data(self, sender, block: BlockResult) -> List[ThorAction]:
        # Incoming swap intentions will be recorded in the DB
        new_swaps = await self.register_new_swaps(block)

        # Swaps and Outs
        interesting_events = list(self.get_events_of_interest(block))

        # To calculate progress and final slip/fees
        await self.register_swap_events(block, interesting_events)

        # Extract finished TX
        txs = await self.detect_swap_finished(block, interesting_events)

        self.dbg_track_swap_id(txs)

        if new_swaps or txs:
            self.logger.info(f"New swaps detected {len(new_swaps)} and {len(txs)} passed in block #{block.block_no}")

        # Pass them down the pipe
        await self.pass_data_to_listeners(txs)

        return txs

    async def register_new_swaps(self, block):
        swaps = self._swap_detector.detect_swaps(block)

        for swap in swaps:
            props = await self._db.read_tx_status(swap.tx_id)
            if not props or not props.attrs.get('status'):
                # self.logger.debug(f'Detect new swap: {swap.tx_id} from {swap.from_address} ({swap.memo})')
                await self._db.write_tx_status_kw(
                    swap.tx_id,
                    id=swap.tx_id,
                    status=SwapProps.STATUS_OBSERVED_IN,
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

        return swaps

    async def register_swap_events(self, block: BlockResult, interesting_events: List[TypeEventSwapAndOut]):
        boom = False

        for swap_ev in interesting_events:
            if not swap_ev.tx_id:
                continue

            hash_key = hash_of_string_repr(swap_ev, block.block_no)[:6]

            if not swap_ev.original:
                self.logger.error(f'Original event is missing for {swap_ev} at block #{block.block_no}')
                continue

            await self._db.write_tx_status(swap_ev.tx_id, {
                f"ev_{swap_ev.original.type}_{hash_key}": swap_ev.original.attrs
            })

            # boom = await self.dbg_on_swap_events(swap_ev, boom)

    @staticmethod
    def get_events_of_interest(block: BlockResult) -> List[TypeEventSwapAndOut]:
        for ev in block.end_block_events:
            swap_ev = parse_swap_and_out_event(ev)
            if swap_ev:
                yield swap_ev

    async def find_tx(self, tx_id) -> Optional[ThorAction]:
        swap_info = await self._db.read_tx_status(tx_id)
        if swap_info:
            tx = swap_info.build_action()
            return tx

    async def detect_swap_finished(self,
                                   block: BlockResult,
                                   interesting_events: List[TypeEventSwapAndOut]) -> List[ThorAction]:
        """
            We do not wait until scheduled outbound will be sent out.
            Swap end is detected by
                a) EventScheduledOutbound
                b) EventOutbound for Rune/synths
        """

        # Group all outbound txs
        group_by_in = defaultdict(list)
        for ev in interesting_events:
            if isinstance(ev, (EventOutbound, EventScheduledOutbound, EventTradeAccountDeposit)):
                group_by_in[ev.tx_id].append(ev)

        results = []
        for tx_id, group in group_by_in.items():
            swap_props = await self._db.read_tx_status(tx_id)
            if not swap_props:
                self.logger.warning(f'There are outbounds for tx {tx_id}, but there is no info about its initiation.')
                continue

            given_away = swap_props.given_away
            if self.dbg_ignore_finished_status:
                given_away = False

            # if no swaps, it is full refund
            if swap_props.is_completed and not given_away:
                # to ignore it in the future
                await self._db.write_tx_status_kw(tx_id, status=SwapProps.STATUS_GIVEN_AWAY)

                results.append(swap_props.build_action())

        if results:
            self.logger.info(f'Give away {len(results)} Txs.')

        return results

    async def build_tx_by_id(self, tx_id):
        swap_props = await self._db.read_tx_status(tx_id)
        if not swap_props:
            raise LookupError(f'Tx {tx_id} not found')
        if not swap_props.is_completed:
            raise ValueError(f'Tx {tx_id} is not completed')
        return swap_props.build_action()

    # ------------------------------------ debug and research ---------------------------------------

    def dbg_open_file(self, filename):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
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
        print(*args, file=s, flush=True)

    def dbg_track_swap_id(self, txs):
        if self.dbg_watch_swap_id:
            if any(tx.tx_hash == self.dbg_watch_swap_id for tx in txs):
                self.dbg_print(f'🎉 Swap finished\n')

    async def dbg_on_swap_events(self, swap_ev: TypeEventSwapAndOut, boom):
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
                self.dbg_print('Scheduled outbound!\n')

        return boom
