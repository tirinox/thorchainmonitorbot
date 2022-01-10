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
        cd_sec = parse_timespan_to_seconds(deps.cfg.as_str('bep2.cooldown', 1))
        self.cd = Cooldown(self.deps.db, 'BEP2Move', cd_sec, max_times=5)
        self.min_usd = deps.cfg.as_float('bep2.min_usd', 1000)
        print('')

    async def on_data(self, sender, transfer: BEP2Transfer):
        rune_price = self.deps.price_holder.usd_per_rune

        if transfer.amount * rune_price >= self.min_usd:
            if await self.cd.can_do():
                await self.deps.broadcaster.notify_preconfigured_channels(
                    BaseLocalization.notification_text_bep2_movement,
                    transfer, rune_price)
