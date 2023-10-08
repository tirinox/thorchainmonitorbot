from typing import List

from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import Asset
from services.lib.utils import WithLogger
from services.models.time_series import TimeSeries
from services.models.transfer import RuneTransfer, RuneCEXFlow


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
        cfg = deps.cfg.get('rune_transfer')

        move_cd_sec = parse_timespan_to_seconds(cfg.as_str('cooldown', 1))
        self.move_cd = Cooldown(self.deps.db, 'RuneMove', move_cd_sec, max_times=5)

        summary_cd_sec = parse_timespan_to_seconds(cfg.as_str('flow_summary.cooldown', 1))
        self.summary_cd = Cooldown(self.deps.db, 'RuneMove.Summary', summary_cd_sec)

        self.min_usd_native = cfg.as_float('min_usd.native', 1000)

        self.cex_list = cfg.as_list('cex_list')
        self.ignore_cex2cex = bool(cfg.get('ignore_cex2cex', True))
        self.tracker = CEXFlowTracker(deps)

    def is_cex2cex(self, transfer: RuneTransfer):
        return self.is_cex(transfer.from_addr) and self.is_cex(transfer.to_addr)

    async def handle_big_transfer(self, transfer: RuneTransfer, usd_per_rune):
        min_usd_amount = self.min_usd_native

        if transfer.amount * usd_per_rune >= min_usd_amount:
            # ignore cex to cex transfers?
            if self.ignore_cex2cex and self.is_cex2cex(transfer):
                self.logger.info(f'Ignoring CEX2CEX transfer: {transfer}')
                return

            if await self.move_cd.can_do():
                await self.move_cd.do()
                await self.pass_data_to_listeners(transfer)

    def _is_to_be_ignored(self, transfer: RuneTransfer):
        if transfer.comment:
            comment = transfer.comment.lower()
            for ignore_comment in self.IGNORE_COMMENTS:
                if ignore_comment in comment:
                    return True

        return False

    def _filter_transfers(self, transfers: List[RuneTransfer]):
        for transfer in transfers:
            if not self._is_to_be_ignored(transfer):
                yield transfer

    def _fill_asset_prices(self, transfers: List[RuneTransfer]):
        usd_per_rune = self.deps.price_holder.usd_per_rune
        for transfer in transfers:
            if transfer.is_rune:
                transfer.usd_per_asset = usd_per_rune
            else:
                pool_name = Asset.from_string(transfer.asset).native_pool_name
                transfer.usd_per_asset = self.deps.price_holder.usd_per_asset(pool_name)
        return transfers

    async def on_data(self, sender, transfers: List[RuneTransfer]):
        usd_per_rune = self.deps.price_holder.usd_per_rune

        transfers = list(self._filter_transfers(transfers))
        transfers = self._fill_asset_prices(transfers)

        for transfer in transfers:
            await self.handle_big_transfer(transfer, usd_per_rune)
            await self._store_transfer(transfer)

        if transfers:
            await self._notify_cex_flow(usd_per_rune)

    async def _notify_cex_flow(self, usd_per_rune):
        if await self.summary_cd.can_do():
            flow = await self.tracker.read_within_period(period=DAY)
            flow.usd_per_rune = usd_per_rune
            await self.summary_cd.do()
            await self.pass_data_to_listeners(flow)

    def is_cex(self, addr):
        return addr in self.cex_list

    async def _store_transfer(self, transfer: RuneTransfer):
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
        self.series = TimeSeries('Rune.CEXFlow', deps.db)

    async def add(self, inflow_amount: float, outflow_amount: float):
        if inflow_amount > 0 or outflow_amount > 0:
            await self.series.add_as_json(j={
                'in': inflow_amount,
                'out': outflow_amount
            })

        await self.series.trim_oldest(self.MAX_POINTS)

    async def read_within_period(self, period=DAY) -> RuneCEXFlow:
        points = await self.series.get_last_values_json(period, max_points=self.MAX_POINTS)
        inflow, outflow = 0.0, 0.0
        for p in points:
            inflow += float(p['in'])
            outflow += float(p['out'])
        overflow = len(points) >= self.MAX_POINTS
        return RuneCEXFlow(inflow, outflow, len(points), overflow,
                           usd_per_rune=self.deps.price_holder.usd_per_rune,
                           period_sec=period)
