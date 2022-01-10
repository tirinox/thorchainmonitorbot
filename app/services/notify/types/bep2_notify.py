import asyncio

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.bep2 import BEP2Transfer


class BEP2MoveNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        cfg = deps.cfg.get('bep2', {})

        cd_sec = parse_timespan_to_seconds(cfg.as_str('cooldown', 1))
        self.cd = Cooldown(self.deps.db, 'BEP2Move', cd_sec, max_times=5)
        self.min_usd = cfg.as_float('min_usd', 1000)
        self.cex_list = cfg.as_list('cex_list')

    async def on_data(self, sender, transfer: BEP2Transfer):
        rune_price = self.deps.price_holder.usd_per_rune

        asyncio.create_task(self._store_transfer(transfer))

        if transfer.amount * rune_price >= self.min_usd:
            if await self.cd.can_do():
                await self.deps.broadcaster.notify_preconfigured_channels(
                    BaseLocalization.notification_text_bep2_movement,
                    transfer, rune_price)

    def is_cex(self, addr):
        return addr in self.cex_list

    async def _store_transfer(self, transfer: BEP2Transfer):
        ...
