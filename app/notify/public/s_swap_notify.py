import asyncio

from jobs.scanner.event_db import EventDatabase
from jobs.scanner.native_scan import BlockResult
from jobs.scanner.swap_start_detector import SwapStartDetector
from lib.constants import THOR_BLOCK_TIME
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.money import pretty_dollar
from lib.utils import safe_get
from models.asset import Asset
from models.s_swap import AlertSwapStart
from notify.dup_stop import TxDeduplicator

DB_KEY_ANNOUNCED_SS_START = 'ss-started:announced-hashes'


class StreamingSwapStartTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, prefix='thor'):
        super().__init__()
        self.deps = deps
        self.prefix = prefix
        self.detector = SwapStartDetector(deps)
        self._ev_db = EventDatabase(deps.db)
        self.min_streaming_swap_usd = self.deps.cfg.as_float(
            'tx.swap.also_trigger_when.streaming_swap.volume_greater', 2500.0)
        self.check_unique = True
        self.logger.info(f'min_streaming_swap_usd = {pretty_dollar(self.min_streaming_swap_usd)}')

        self.deduplicator = TxDeduplicator(deps.db, DB_KEY_ANNOUNCED_SS_START)

    async def on_data(self, sender, data: BlockResult):
        if self.min_streaming_swap_usd <= 0.0:
            return

        ph = await self.deps.pool_cache.get()
        swaps = self.detector.detect_swaps(data, ph)

        self.logger.info(f'Found {len(swaps)} swap starts in block #{data.block_no}')

        for swap_start_ev in swaps:
            if await self.is_swap_eligible(swap_start_ev):
                await self._relay_new_event(swap_start_ev)

    async def is_swap_eligible(self, swap_start_ev: AlertSwapStart):
        e = swap_start_ev

        # todo: switch to "debug"
        log_f = self.logger.debug

        if not e.is_streaming:
            log_f(f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: not streaming')
            return False

        if e.volume_usd < self.min_streaming_swap_usd:
            log_f(f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: {e.volume_usd = } < {self.min_streaming_swap_usd}')
            return False

        if self.check_unique:
            if await self.deduplicator.have_ever_seen_hash(e.tx_id):
                log_f(f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: already seen')
                return False

        self.logger.info(f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: eligible')
        return True

    async def _relay_new_event(self, event: AlertSwapStart):
        await asyncio.sleep(THOR_BLOCK_TIME * 1.1)  # Sleep 1 block to ensure the tx appears in the blockchain

        await self.load_extra_tx_information(event)
        self._correct_streaming_swap_info(event)
        if event.is_streaming:
            await self.deduplicator.mark_as_seen(event.tx_id)

        await self.pass_data_to_listeners(event)  # alert!

    async def load_extra_tx_information(self, event: AlertSwapStart):
        try:
            event.status = await self.deps.thor_connector.query_tx_status(event.tx_id)

            ss = event.status.get_streaming_swap()
            if ss:
                event.ss = event.ss._replace(
                    interval=ss.get('interval', 0),
                    quantity=ss.get('quantity', 0),
                    count=ss.get('count', 0),
                )
            else:
                self.logger.warning(f'No streaming swap info in status for {event.tx_id}')

        except Exception as e:
            self.logger.warning(f'Failed to load status for {event.tx_id}: {e}')

        try:
            event.clout = await self.deps.thor_connector.query_swapper_clout(event.from_address)
        except Exception as e:
            self.logger.warning(f'Failed to load clout for {event.tx_id}: {e}')

        await self.load_quote(event)
        return event

    async def load_quote(self, event: AlertSwapStart):
        try:
            from_asset = str(Asset(event.in_asset).l1_asset)
            to_asset = str(Asset(event.out_asset).l1_asset)
            event.quote = await self.deps.thor_connector.query_swap_quote(
                from_asset=from_asset,
                to_asset=to_asset,
                amount=event.in_amount,
                # refund_address=event.from_address,
                streaming_quantity=event.ss.quantity,
                streaming_interval=event.ss.interval,
                tolerance_bps=10000,  # MAX
                # affiliate='t' if event.memo.affiliates else '',  # does not matter for quote
                affiliate_bps=event.memo.affiliate_fee_bp,
                height=event.block_height,  # for historical quotes
            )
        except Exception as e:
            self.logger.warning(f'Failed to load quote for {event.tx_id}: {e}')

    def _correct_streaming_swap_info(self, event: AlertSwapStart):
        if event.ss and event.ss.quantity == 0 and event.ss.interval > 0:
            if event.status:
                new_quantity = safe_get(event.status.stages, 'swap_status', 'streaming', 'quantity')
                if new_quantity:
                    self.logger.info(f'Updated SS quantity {event.ss.quantity} => {new_quantity}')
                    event.ss = event.ss._replace(quantity=new_quantity)
