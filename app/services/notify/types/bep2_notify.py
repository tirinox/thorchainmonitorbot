import asyncio

from localization import BaseLocalization
from services.jobs.fetch.base import INotified, WithDelegates
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.bep2 import BEP2Transfer, BEP2CEXFlow
from services.models.time_series import TimeSeries


class BEP2MoveNotifier(INotified, WithDelegates):
    def __init__(self, deps: DepContainer):
        super().__init__()

        self.deps = deps
        self.logger = class_logger(self)
        cfg = deps.cfg.get('bep2')

        move_cd_sec = parse_timespan_to_seconds(cfg.as_str('cooldown', 1))
        self.move_cd = Cooldown(self.deps.db, 'BEP2Move', move_cd_sec, max_times=5)

        summary_cd_sec = parse_timespan_to_seconds(cfg.as_str('flow_summary.cooldown', 1))
        self.summary_cd = Cooldown(self.deps.db, 'BEP2Move.Summary', summary_cd_sec)

        self.min_usd = cfg.as_float('min_usd', 1000)
        self.cex_list = cfg.as_list('cex_list')
        self.tracker = CEXFlowTracker(deps)

    async def on_data(self, sender, transfer: BEP2Transfer):
        transfer.usd_per_rune = usd_per_rune = self.deps.price_holder.usd_per_rune

        asyncio.create_task(self._store_transfer(transfer))

        if transfer.amount * usd_per_rune >= self.min_usd:
            if await self.move_cd.can_do():
                await self.move_cd.do()
                await self.handle_data(transfer)

        if await self.summary_cd.can_do():
            notifier: BEP2MoveNotifier = self.deps.bep2_move_notifier
            flow = await notifier.tracker.read_last24h()
            flow.usd_per_rune = usd_per_rune
            await self.summary_cd.do()
            await self.handle_data(flow)

    def is_cex(self, addr):
        return addr in self.cex_list

    async def _store_transfer(self, transfer: BEP2Transfer):
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
        self.series = TimeSeries('CEXFlow.BEP2', deps.db)

    async def add(self, inflow_amount: float, outflow_amount: float):
        if inflow_amount > 0 or outflow_amount > 0:
            await self.series.add_as_json(j={
                'in': inflow_amount,
                'out': outflow_amount
            })

        await self.series.trim_oldest(self.MAX_POINTS)

    async def read_last24h(self) -> BEP2CEXFlow:
        points = await self.series.get_last_values_json(DAY, max_points=self.MAX_POINTS)
        inflow, outflow = 0.0, 0.0
        for p in points:
            inflow += float(p['in'])
            outflow += float(p['out'])
        overflow = len(points) >= self.MAX_POINTS
        return BEP2CEXFlow(inflow, outflow, len(points), overflow)
