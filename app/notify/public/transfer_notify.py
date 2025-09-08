from contextlib import suppress
from typing import List

from jobs.scanner.arb_detector import ArbBotDetector
from lib.constants import SYNTH_MODULE
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.asset import Asset
from models.price import PriceHolder
from models.transfer import NativeTokenTransfer


class RuneMoveNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()

        self.deps = deps
        cfg = deps.cfg.get('token_transfer')

        move_cd_sec = parse_timespan_to_seconds(cfg.as_str('cooldown', 1))
        self.move_cd = Cooldown(self.deps.db, 'RuneMove', move_cd_sec, max_times=5)
        self.min_usd_native = cfg.as_float('min_usd.native', 1000)

        self.cex_list = cfg.as_list('cex_list')
        self.ignore_cex2cex = bool(cfg.get('ignore_cex2cex', True))
        self.arb_detector = ArbBotDetector(deps)
        self.hide_arb_bots = cfg.as_bool('hide_arbitrage_bots', True)

    def is_cex2cex(self, transfer: NativeTokenTransfer):
        return self.is_cex(transfer.from_addr) and self.is_cex(transfer.to_addr)

    def is_cex(self, addr):
        return addr in self.cex_list

    async def handle_transfer(self, transfer: NativeTokenTransfer, usd_per_rune):
        # compare against min_usd_amount threshold
        min_usd_amount = self.min_usd_native
        if transfer.amount * usd_per_rune >= min_usd_amount:
            if await self.move_cd.can_do():
                await self.move_cd.do()

                with suppress(Exception):
                    await self.arb_detector.try_to_detect_arb_bot(transfer.from_addr)
                    await self.arb_detector.try_to_detect_arb_bot(transfer.to_addr)

                await self.pass_data_to_listeners(transfer)

    async def _is_to_be_ignored(self, transfer: NativeTokenTransfer):
        if transfer.is_comment_non_send():
            self.logger.debug(f'Ignore comment: {transfer.comment} in {transfer}')
            return True

        if self.hide_arb_bots:
            if await self.arb_detector.is_marked_as_arb(transfer.from_addr):
                self.logger.debug(f'Ignore arb bot: from address = {transfer.from_addr}')
                return True
            if await self.arb_detector.is_marked_as_arb(transfer.to_addr):
                self.logger.debug(f'Ignore arb bot: to address = {transfer.to_addr}')
                return True

        # bug fix, ignore tcy stake and similar things
        if transfer.to_addr == SYNTH_MODULE:
            self.logger.debug(f"Ignore deposits to SYNTH_MODULE: {transfer}")
            return True

        # ignore cex to cex transfers?
        if self.ignore_cex2cex and self.is_cex2cex(transfer):
            self.logger.debug(f'Ignoring CEX2CEX transfer: {transfer}')
            return True

        return False

    async def _filter_transfers(self, transfers: List[NativeTokenTransfer]):
        results = []
        for transfer in transfers:
            if not await self._is_to_be_ignored(transfer):
                results.append(transfer)
        return results

    @staticmethod
    def _fill_asset_prices(transfers: List[NativeTokenTransfer], ph: PriceHolder):
        usd_per_rune = ph.usd_per_rune
        for transfer in transfers:
            if transfer.is_rune:
                transfer.usd_per_asset = usd_per_rune
            else:
                pool_name = Asset.from_string(transfer.asset).native_pool_name
                transfer.usd_per_asset = ph.usd_per_asset(pool_name)
        return transfers

    async def on_data(self, sender, all_transfers: List[NativeTokenTransfer]):
        transfers = list(await self._filter_transfers(all_transfers))

        ph = await self.deps.pool_cache.get()
        transfers = self._fill_asset_prices(transfers, ph)

        for transfer in transfers:
            try:
                await self.handle_transfer(transfer, ph.usd_per_rune)
            except Exception as e:
                self.logger.exception(f"Error handling transfer: {e}", exc_info=e)
