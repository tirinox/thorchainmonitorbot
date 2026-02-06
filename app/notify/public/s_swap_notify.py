from jobs.scanner.arb_detector import ArbBotDetector, ArbStatus
from jobs.scanner.event_db import EventDatabase
from lib.constants import float_to_thor
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.money import pretty_dollar
from models.asset import Asset
from models.s_swap import AlertSwapStart
from notify.dup_stop import TxDeduplicator

DB_KEY_ANNOUNCED_SS_START = 'ss-started:announced-hashes'


class StreamingSwapStartTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._ev_db = EventDatabase(deps.db)
        self.min_streaming_swap_usd = self.deps.cfg.as_float(
            'tx.swap.also_trigger_when.streaming_swap.volume_greater', 2500.0)
        self.check_unique = True
        self.logger.info(f'min_streaming_swap_usd = {pretty_dollar(self.min_streaming_swap_usd)}')
        self.hide_arb_bots = self.deps.cfg.as_bool('tx.swap.hide_arbitrage_bots', True)
        self.arb_detector = ArbBotDetector(deps)

        self.deduplicator = TxDeduplicator(deps.db, DB_KEY_ANNOUNCED_SS_START)

    async def on_data(self, sender, event: AlertSwapStart):
        if not await self.is_swap_eligible(event):
            return

        await self.load_extra_tx_information(event)
        await self.deduplicator.mark_as_seen(event.tx_id)
        await self.pass_data_to_listeners(event)  # alert!

    async def is_swap_eligible(self, swap_start_ev: AlertSwapStart):
        e = swap_start_ev

        log_f = self.logger.debug

        if e.is_limit:
            # fixme
            return False

        if not e.is_streaming:
            log_f(f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: not streaming')
            return False

        if self.hide_arb_bots:
            sender = swap_start_ev.from_address
            if await self.arb_detector.try_to_detect_arb_bot(sender) == ArbStatus.ARB:
                self.logger.warning(f'Ignoring Tx from Arb bot: {swap_start_ev.tx_id} by {sender}')
                return False

        if e.volume_usd < self.min_streaming_swap_usd:
            log_f(
                f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: {e.volume_usd = } < {self.min_streaming_swap_usd}')
            return False

        if self.check_unique:
            if await self.deduplicator.have_ever_seen_hash(e.tx_id):
                log_f(f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: already seen')
                return False

        self.logger.info(f'Swap start {e.tx_id}: {e.in_asset} -> {e.out_asset}: eligible')
        return True

    async def load_extra_tx_information(self, event: AlertSwapStart):
        try:
            event.clout = await self.deps.thor_connector.query_swapper_clout(event.from_address)
        except Exception as e:
            self.logger.warning(f'Failed to load clout for {event.tx_id}: {e}')

        await self.load_quote(event)
        return event

    async def load_quote(self, event: AlertSwapStart):
        try:
            from_asset = str(Asset(event.in_asset))
            to_asset = str(Asset(event.out_asset))
            event.quote = await self.deps.thor_connector.query_swap_quote(
                from_asset=from_asset,
                to_asset=to_asset,
                amount=float_to_thor(event.in_amount),
                # refund_address=event.from_address,
                destination=event.destination_address,
                streaming_quantity=event.quantity,
                streaming_interval=event.interval,
                tolerance_bps=10000,  # MAX
                affiliate='t' if event.memo.affiliates else '',  # does not matter for quote
                affiliate_bps=event.memo.affiliate_fee_bp,
                height=event.block_height,  # for historical quotes
            )
            if err_msg := event.quote.get('message'):
                self.logger.warning(f'Failed to load quote for {event.tx_id}: {err_msg}')
        except Exception as e:
            self.logger.error(f'Failed to load quote for {event.tx_id}: {e}')
