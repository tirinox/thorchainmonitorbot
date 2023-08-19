import datetime
import sys
from collections import defaultdict
from typing import List

from services.jobs.affiliate_merge import ZERO_HASH
from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.native_scan import BlockResult
from services.jobs.scanner.swap_props import SwapProps
from services.jobs.scanner.swap_start_detector import SwapStartDetector
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger, say, hash_of_string_repr
from services.models.s_swap import parse_swap_and_out_event, EventSwapStart, EventOutbound, \
    EventScheduledOutbound, TypeEventSwapAndOut, EventSwap
from services.models.tx import ThorTx


class NativeActionExtractor(WithDelegates, INotified, WithLogger):
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

        self.clean_block_older_than_block = deps.cfg.as_int('native_scanner.clean_block_older_than_block', 0)

    async def _do_clean(self):
        if self.clean_block_older_than_block <= 0:
            return

        last_block = self.deps.last_block_store.thor
        if not last_block:
            return

        oldest_block = last_block - self.clean_block_older_than_block

        await self._db.clean_up_old_events(oldest_block)

    async def on_data(self, sender, block: BlockResult) -> List[ThorTx]:
        new_swaps = self._swap_detector.detect_swaps(block)

        await self._do_clean()

        # Incoming swap intentions will be recorded in the DB
        await self.register_new_swaps(new_swaps, block.block_no)

        # # todo: debug
        # for swap in new_swaps:
        #     if swap.memo.affiliate_address:
        #         print(f"{swap.in_amount} {swap.in_asset} => {swap.memo_str} ({swap.memo.affiliate_address}/{swap.memo.affiliate_fee})")
        #         if swap.memo.affiliate_fee and swap.out_asset == 'THOR.RUNE':
        #             await say('Feeeeeee!')
        #             print(swap.tx_id, ' /// ', swap.block_height)
        #             exit(0)
        # if swap.memo.affiliate_fee and swap.in_asset.upper().startswith('BNB'):
        #         await say('Interesting!')
        #         print('stop')

        # Swaps and Outs
        interesting_events = list(self.get_events_of_interest(block))

        # To calculate progress and final slip/fees
        await self.register_swap_events(block, interesting_events)

        # Extract finished TX
        txs = await self.detect_swap_finished(block, interesting_events)

        # Pass them down the pipe
        await self.pass_data_to_listeners(txs)

    async def register_new_swaps(self, swaps: List[EventSwapStart], height):
        self.logger.info(f"New swaps {len(swaps)} in block #{height}")

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

    @staticmethod
    def suspect_outbound_internal(ev: EventOutbound):
        return ev.out_id == ZERO_HASH and ev.chain == 'THOR'

    def do_write_event(self, tx_id):
        return not self.dbg_watch_swap_id or self.dbg_watch_swap_id == tx_id

    async def register_swap_events(self, block: BlockResult, interesting_events: List[TypeEventSwapAndOut]):
        boom = False
        for swap_ev in interesting_events:
            hash_key = hash_of_string_repr(swap_ev, block.block_no)

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

        # Group all outbound txs
        group_by_in = defaultdict(list)
        for ev in interesting_events:
            if isinstance(ev, (EventOutbound, EventScheduledOutbound)):
                group_by_in[ev.tx_id].append(ev)

        results = []
        for tx_id, group in group_by_in.items():
            swap_info = await self._db.read_tx_status(tx_id)
            if not swap_info:
                self.logger.warning(f'There are outbounds for tx {tx_id}, but there is no info about its initiation.')
                continue

            # print(f'{tx_id}: {swap_info.has_started = }, {swap_info.has_swaps = }, '
            #       f'{swap_info.is_finished = }, {swap_info.given_away = }')

            # if no swaps, it is full refund
            if swap_info.has_started and swap_info.has_swaps and swap_info.is_finished and not swap_info.given_away:
                # to ignore it in the future
                await self._db.write_tx_status_kw(tx_id, status=SwapProps.STATUS_GIVEN_AWAY)

                tx = swap_info.build_tx()
                results.append(tx)

        if results:
            self.logger.info(f'Give away {len(results)} Txs.')

        return results

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
