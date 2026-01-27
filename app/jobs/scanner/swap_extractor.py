import datetime
import os
import sys
from typing import List

from jobs.scanner.event_db import EventDatabase
from jobs.scanner.native_scan import BlockResult
from jobs.scanner.swap_props import SwapProps
from jobs.scanner.swap_start_detector import SwapStartDetector
from jobs.scanner.tx import ThorObservedTx, ThorEvent
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import hash_of_string_repr, say
from models.events import EventOutbound, EventScheduledOutbound, \
    parse_swap_and_out_event, TypeEventSwapAndOut, EventSwap
from models.tx import ThorAction


def _consists_only_zeros(s):
    return len(s) > 0 and all(char == '0' for char in s)


class SwapExtractorBlock(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._swap_detector = SwapStartDetector(deps)

        expiration_sec = deps.cfg.as_interval('native_scanner.db.ttl', '3d')
        self._db = EventDatabase(deps.db, expiration_sec=expiration_sec)

        self._dbg_init()

    async def on_data(self, sender, block: BlockResult) -> List[ThorAction]:
        # Incoming swap intentions will be recorded in the DB
        new_swaps = await self.register_new_swaps(block)

        # Swaps and Outbounds
        interesting_end_block_events = list(self.get_end_block_events_of_interest(block))

        # Collect a set of original in_tx_id for end block outbounds
        end_block_outbounds_tx_ids = set(
            ev.tx_id for ev in interesting_end_block_events if isinstance(ev, EventOutbound))

        # Also get quorum observed outbounds
        outbound_tx_id_set, outbound_events = self.detect_observed_quorum_outbounds(block)

        # Write them into the DB
        await self.register_swap_events(block, interesting_end_block_events)
        await self.register_swap_events(block, outbound_events)

        # Extract finished TX from these two sources
        all_outbounds_tx_id_set = end_block_outbounds_tx_ids | outbound_tx_id_set
        txs = await self.handle_finished_swaps(all_outbounds_tx_id_set)

        self.dbg_track_swap_id(txs)

        if new_swaps or txs:
            self.logger.info(f"New swaps detected {len(new_swaps)} and {len(txs)} passed in block #{block.block_no}")

        # Pass them down the pipe
        await self.pass_data_to_listeners(txs)

        return txs

    async def register_new_swaps(self, block):
        ph = await self.deps.pool_cache.get()
        swaps = self._swap_detector.detect_swaps(block, ph)

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
            await self.dbg_on_new_swap(swap)

        return swaps

    @staticmethod
    def _event_ident(event, block_no):
        if hasattr(event, "out_id") and not _consists_only_zeros(event.out_id):
            # use existing tx_id to make our idents
            hash_key = event.out_id
        else:
            # just hash of object
            hash_key = hash_of_string_repr(event, block_no)

        short_hash_key = hash_key[:6]  # 4 is not enough, 1000
        # block_id = int(block_no) % 10_000
        # return f"ev_{event.original.type}_{block_id}_{short_hash_key}"
        # bugfix: with high outbound value!
        return f"ev_{event.original.type}_{short_hash_key}"

    async def register_swap_events(self, block: BlockResult, interesting_events: List[TypeEventSwapAndOut]):
        for event in interesting_events:
            if not event.tx_id:
                continue

            if not event.original:
                self.logger.error(f'Original event is missing for {event} at block #{block.block_no}')
                continue

            event_ident = self._event_ident(event, block.block_no)
            await self._db.write_tx_status(event.tx_id, {
                event_ident: event.original.attrs
            })

            # boom = await self.dbg_on_swap_events(swap_ev, boom)

    @staticmethod
    def get_end_block_events_of_interest(block: BlockResult):
        for ev in block.end_block_events:
            swap_ev = parse_swap_and_out_event(ev)
            if swap_ev:
                yield swap_ev

    def make_events_from_observed_tx(self, tx: ThorObservedTx):
        if not tx.is_outbound:
            self.logger.error("Cannot create EventOutbound from inbound transaction")
            return

        memo = (tx.memo or '').upper()
        if memo.startswith('MIGRATE') or memo.startswith('CONSOLIDATE'):
            self.logger.debug(f"Internal tx {tx.memo} is ignored.")
            return

        if not (memo.startswith('OUT:') or memo.startswith('REFUND:')):
            self.logger.warning(f"Cannot create EventOutbound from tx with memo: {tx.memo!r}")
            return

        real_in_tx = tx.memo.split(':')[1]

        for coin in tx.coins:
            yield EventOutbound.from_event(ThorEvent({
                'id': tx.tx_id,
                'chain': tx.chain,
                'in_tx_id': real_in_tx,
                'from': tx.from_address,
                'to': tx.to_address,
                'coin': f"{coin.asset} {coin.amount}",
                'memo': tx.memo,
                'type': 'outbound',
                '_height': tx.block_height,
                '_amount': coin.amount,
                '_asset': coin.asset,
            }))

    def detect_observed_quorum_outbounds(self, block: BlockResult):
        completed_txs_ids = set()
        events = []
        for tx in block.all_observed_txs:
            if tx.is_outbound:
                events = list(self.make_events_from_observed_tx(tx))
                events.extend(events)
                # EventOutbound.tx_id is the original inbound tx id (in_tx_id field)
                completed_txs_ids.update(e.tx_id for e in events)
        return completed_txs_ids, events

    async def handle_finished_swaps(self, outbound_tx_id_set: set) -> List[ThorAction]:
        """
        Outbound can come from end_block_events or from observed quorum txs.
        """
        results = []

        for tx_id in outbound_tx_id_set:
            swap_props = await self._db.read_tx_status(tx_id)
            if not swap_props:
                self.logger.warning(f'There are outbounds for tx {tx_id}, but there is no info about its initiation.')
                continue

            given_away = swap_props.given_away
            if self.dbg_ignore_finished_status:
                given_away = False

            # Check if the swap is completed and not given away
            if swap_props.is_completed and not given_away:
                # Update the status to avoid double processing in the future
                await self._db.write_tx_status_kw(tx_id, status=SwapProps.STATUS_GIVEN_AWAY)

                # Find out the timestamp of the swap from the block height
                ts = await self._get_ts_from_swap_props(swap_props, tx_id)

                # Build a ThorAction and put it into the results
                action = swap_props.build_action(ts)
                results.append(action)

        if results:
            self.logger.info(f'Give away {len(results)} Txs.')

        return results

    async def _get_ts_from_swap_props(self, swap_props: SwapProps, tx_id):
        height = int(swap_props.attrs.get('block_height', 0))
        if height:
            ts = await self.deps.last_block_cache.get_timestamp_of_block(height)
        else:
            ts = datetime.datetime.now().timestamp()
            self.logger.debug(f'No timestamp for TX {tx_id}, using now {ts}')
        return ts

    async def build_tx_from_database(self, tx_id):
        swap_props = await self._db.read_tx_status(tx_id)

        ts = await self._get_ts_from_swap_props(swap_props, tx_id)

        if not swap_props:
            raise LookupError(f'Tx {tx_id} not found')
        if not swap_props.is_completed:
            raise ValueError(f'Tx {tx_id} is not completed')
        return swap_props.build_action(ts)

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

    async def dbg_on_new_swap(self, swap):
        if swap.tx_id == self.dbg_watch_swap_id and not self.dbg_start_observed:
            self.dbg_print(f'👿 Start watching swap\n')
            self.dbg_print(swap, '\n\n')

            await say('Found a swap')

            self.dbg_start_observed = True

    def _dbg_init(self):
        self.dbg_watch_swap_id = None
        self.dbg_start_observed = False
        self.dbg_start_time = datetime.datetime.now()
        self.dbg_swaps = 0
        self.dbg_file = None
        self.dbg_ignore_finished_status = False
