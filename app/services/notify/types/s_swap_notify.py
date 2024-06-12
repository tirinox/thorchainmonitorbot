from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.native_scan import BlockResult
from services.jobs.scanner.swap_start_detector import SwapStartDetector
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import pretty_dollar
from services.lib.utils import WithLogger, safe_get
from services.models.s_swap import AlertSwapStart
from services.notify.dup_stop import TxDeduplicator

DB_KEY_ANNOUNCED_SS_START = 'tx:ss-started:announced-hashes'


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

        swaps = self.detector.detect_swaps(data)

        self.logger.info(f'Found {len(swaps)} swap starts in block #{data.block_no}')

        for swap_start_ev in swaps:
            if await self.is_swap_eligible(swap_start_ev):
                await self._relay_new_event(swap_start_ev)

    async def is_swap_eligible(self, swap_start_ev):
        # print(f'Swap {swap_start_ev.is_streaming = }, {swap_start_ev.volume_usd = }')

        if not swap_start_ev.is_streaming:
            return False

        if swap_start_ev.volume_usd < self.min_streaming_swap_usd:
            return False

        if self.check_unique:
            if await self.deduplicator.have_ever_seen_hash(swap_start_ev.tx_id):
                return False

        return True

    async def _relay_new_event(self, event: AlertSwapStart):
        await self._load_status_info(event)
        self._correct_streaming_swap_info(event)
        await self.deduplicator.mark_as_seen(event.tx_id)
        await self.pass_data_to_listeners(event)

    async def _load_status_info(self, event: AlertSwapStart):
        try:
            event.status = await self.deps.thor_connector.query_tx_status(event.tx_id)
        except Exception as e:
            self.logger.warning(f'Failed to load status for {event.tx_id}: {e}')

        try:
            event.clout = await self.deps.thor_connector.query_swapper_clout(event.from_address)
        except Exception as e:
            self.logger.warning(f'Failed to load clout for {event.tx_id}: {e}')

    def _correct_streaming_swap_info(self, event: AlertSwapStart):
        if event.ss and event.ss.quantity == 0 and event.ss.interval > 0:
            if event.status:
                new_quantity = safe_get(event.status.stages, 'swap_status', 'streaming', 'quantity')
                if new_quantity:
                    self.logger.info(f'Updated SS quantity {event.ss.quantity} => {new_quantity}')
                    event.ss = event.ss._replace(quantity=new_quantity)
