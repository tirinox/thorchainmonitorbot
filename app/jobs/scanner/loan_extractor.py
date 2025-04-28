from contextlib import suppress

from jobs.scanner.event_db import EventDatabase
from jobs.scanner.native_scan import BlockResult
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.events import parse_swap_and_out_event, EventLoanOpen, EventLoanRepayment
from models.loans import AlertLoanOpen, AlertLoanRepayment


class LoanExtractorBlock(WithLogger, WithDelegates, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._db = EventDatabase(deps.db)

    async def on_data(self, sender, block: BlockResult):
        with suppress(Exception):
            await self._handle_data_unsafe(block)

    async def _handle_data_unsafe(self, block: BlockResult):
        results = []
        ph = self.deps.price_holder

        for e in block.end_block_events:
            event = parse_swap_and_out_event(e)

            if isinstance(event, EventLoanOpen):
                target_price_usd = ph.get_asset_price_in_usd(event.target_asset)
                collateral_price_usd = ph.get_asset_price_in_usd(event.collateral_asset)
                alert = AlertLoanOpen(
                    tx_id='',  # fixme: acquire tx id
                    loan=event,
                    target_price_usd=target_price_usd,
                    collateral_price_usd=collateral_price_usd
                )
                results.append(alert)

            elif isinstance(event, EventLoanRepayment):
                collateral_price_usd = ph.get_asset_price_in_usd(event.collateral_asset)
                alert = AlertLoanRepayment(
                    tx_id='',  # fixme: acquire tx id
                    loan=event,
                    collateral_price_usd=collateral_price_usd
                )
                results.append(alert)

        await self.pass_data_to_listeners(results)
