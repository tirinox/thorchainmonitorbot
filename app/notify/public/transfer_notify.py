from contextlib import suppress
from typing import List

from jobs.scanner.arb_detector import ArbBotDetector
from lib.constants import SYNTH_MODULE
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds, DAY
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.asset import Asset
from models.price import PriceHolder
from models.time_series import TimeSeries
from models.transfer import NativeTokenTransfer, RuneCEXFlow


class RuneMoveNotifier(INotified, WithDelegates, WithLogger):
    IGNORE_COMMENTS = (
        'deposit',
        'outbound',
        'solvency',
        'observedtxout',
        'observedtxin',
    )

    def __init__(self, deps: DepContainer):
        super().__init__()

        self.deps = deps
        cfg = deps.cfg.get('token_transfer')

        move_cd_sec = parse_timespan_to_seconds(cfg.as_str('cooldown', 1))
        self.move_cd = Cooldown(self.deps.db, 'RuneMove', move_cd_sec, max_times=5)

        self.flow_enabled = cfg.get_pure('flow_summary.enabled', True)
        summary_cd_sec = parse_timespan_to_seconds(cfg.as_str('flow_summary.cooldown', 1))
        self.summary_cd = Cooldown(self.deps.db, 'RuneMove.Summary', summary_cd_sec)

        self.min_usd_native = cfg.as_float('min_usd.native', 1000)

        self.cex_list = cfg.as_list('cex_list')
        self.ignore_cex2cex = bool(cfg.get('ignore_cex2cex', True))
        self.tracker = CEXFlowTracker(deps)
        self.arb_detector = ArbBotDetector(deps)

    def is_cex2cex(self, transfer: NativeTokenTransfer):
        return self.is_cex(transfer.from_addr) and self.is_cex(transfer.to_addr)

    async def handle_big_transfer(self, transfer: NativeTokenTransfer, usd_per_rune):
        # compare against min_usd_amount threshold
        min_usd_amount = self.min_usd_native
        if transfer.amount * usd_per_rune >= min_usd_amount:
            if await self.move_cd.can_do():
                await self.move_cd.do()

                with suppress(Exception):
                    await self.arb_detector.try_to_detect_arb_bot(transfer.from_addr)
                    await self.arb_detector.try_to_detect_arb_bot(transfer.to_addr)

                await self.pass_data_to_listeners(transfer)

    def _is_to_be_ignored(self, transfer: NativeTokenTransfer):
        if transfer.comment:
            comment = transfer.comment.lower()
            for ignore_comment in self.IGNORE_COMMENTS:
                # fixme issue: bond is deposit, it is ignored
                if ignore_comment in comment:
                    self.logger.debug(f'ignore comment: {comment} in {transfer}')
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

    def _filter_transfers(self, transfers: List[NativeTokenTransfer]):
        for transfer in transfers:
            if not self._is_to_be_ignored(transfer):
                yield transfer

    def _fill_asset_prices(self, transfers: List[NativeTokenTransfer], ph: PriceHolder):
        usd_per_rune = ph.usd_per_rune
        for transfer in transfers:
            if transfer.is_rune:
                transfer.usd_per_asset = usd_per_rune
            else:
                pool_name = Asset.from_string(transfer.asset).native_pool_name
                transfer.usd_per_asset = ph.usd_per_asset(pool_name)
        return transfers

    async def on_data(self, sender, transfers: List[NativeTokenTransfer]):
        ph = await self.deps.pool_cache.get()
        transfers = list(self._filter_transfers(transfers))
        transfers = self._fill_asset_prices(transfers, ph)

        for transfer in transfers:
            try:
                await self.handle_big_transfer(transfer, ph.usd_per_rune)
            except Exception as e:
                self.logger.exception(f"Error handling transfer: {e}", exc_info=e)

            await self._store_transfer(transfer)

        if self.flow_enabled:
            if transfers:
                await self._notify_cex_flow(ph.usd_per_rune)

    async def _notify_cex_flow(self, usd_per_rune):
        if await self.summary_cd.can_do():
            flow = await self.tracker.read_within_period(period=DAY)
            flow.usd_per_rune = usd_per_rune
            await self.summary_cd.do()
            await self.pass_data_to_listeners(flow)

    def is_cex(self, addr):
        return addr in self.cex_list

    async def _store_transfer(self, transfer: NativeTokenTransfer):
        if not transfer.is_rune:
            return

        inflow, outflow = 0.0, 0.0
        if self.is_cex(transfer.from_addr):
            outflow = transfer.amount
        if self.is_cex(transfer.to_addr):
            inflow = transfer.amount
        await self.tracker.add(inflow, outflow)


class CEXFlowTracker:
    MAX_POINTS = 100000

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.series = TimeSeries('Rune.CEXFlow', deps.db, self.MAX_POINTS)

    async def add(self, inflow_amount: float, outflow_amount: float):
        if inflow_amount > 0 or outflow_amount > 0:
            await self.series.add_as_json(j={
                'in': inflow_amount,
                'out': outflow_amount
            })

    async def read_within_period(self, period=DAY) -> RuneCEXFlow:
        points = await self.series.get_last_values_json(period, max_points=self.MAX_POINTS)
        inflow, outflow = 0.0, 0.0
        for p in points:
            inflow += float(p['in'])
            outflow += float(p['out'])
        overflow = len(points) >= self.MAX_POINTS
        usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()
        return RuneCEXFlow(
            inflow, outflow,
            len(points),
            overflow,
            usd_per_rune=usd_per_rune,
            period_sec=period
        )
