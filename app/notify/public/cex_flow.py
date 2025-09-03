from typing import List

from lib.constants import SYNTH_MODULE
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds, DAY
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.time_series import TimeSeries
from models.transfer import NativeTokenTransfer, RuneCEXFlow


class CEXFlowNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()

        self.deps = deps

        cfg = deps.cfg.get('token_transfer')
        self.flow_enabled = cfg.get_pure('flow_summary.enabled', True)
        self.min_rune_in_summary = cfg.as_float('flow_summary.min_rune_sum', 10_000)
        summary_cd_sec = parse_timespan_to_seconds(cfg.as_str('flow_summary.cooldown', 1))
        self.summary_cd = Cooldown(self.deps.db, 'RuneMove.Summary', summary_cd_sec)

        self.cex_list = cfg.as_list('cex_list')
        self.ignore_cex2cex = bool(cfg.get('ignore_cex2cex', True))

        self.series = TimeSeries('Rune.CEXFlow', deps.db, self.MAX_POINTS)

    async def _is_to_be_ignored(self, transfer: NativeTokenTransfer):
        if transfer.is_comment_non_send():
            self.logger.debug(f'Ignore comment: {transfer.comment} in {transfer}')
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

    def is_cex2cex(self, transfer: NativeTokenTransfer):
        return self.is_cex(transfer.from_addr) and self.is_cex(transfer.to_addr)

    async def on_data(self, sender, transfers: List[NativeTokenTransfer]):
        for transfer in transfers:
            await self._store_transfer(transfer)
        await self._notify_cex_flow()

    async def _notify_cex_flow(self):
        if await self.summary_cd.can_do():
            flow = await self.read_within_period(period=DAY)
            if not flow:
                self.deps.emergency.report('CEXFlow', 'No CEX flow')
                return

            await self.summary_cd.do()

            if flow.total_rune < self.min_rune_in_summary:
                self.deps.emergency.report(
                    'CEXFlow', 'CEX flow aggregation does not look good.',
                    flow=flow,
                    min_rune=self.min_rune_in_summary
                )
                return

            ph = await self.deps.pool_cache.get()
            flow.usd_per_rune = ph.usd_per_rune

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
        await self._add_point(inflow, outflow)

    MAX_POINTS = 100000

    async def _add_point(self, inflow_amount: float, outflow_amount: float):
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
