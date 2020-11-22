import logging

from localization import LocalizationManager, BaseLocalization
from services.fetch.base import INotified
from services.fetch.queue import QueueInfo
from services.lib.config import Config
from services.lib.cooldown import CooldownTracker
from services.lib.db import DB
from services.models.time_series import PriceTimeSeries
from services.notify.broadcast import Broadcaster

QUEUE_STREAM = 'QUEUE'


class QueueNotifier(INotified):
    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, loc_man: LocalizationManager):
        self.cfg = cfg
        self.broadcaster = broadcaster
        self.logger = logging.getLogger('QueueNotifier')
        self.loc_man = loc_man
        self.cooldown_tracker = CooldownTracker(db)
        self.cooldown = cfg.queue.cooldown
        self.threshold = cfg.queue.steps[0]
        self.logger.info(f'config: {cfg.queue}')
        self.steps = tuple(map(int, cfg.queue.steps))

        self.time_series = PriceTimeSeries(QUEUE_STREAM, db)

    async def notify(self, item_type, step, value):
        await self.broadcaster.notify_preconfigured_channels(self.loc_man,
                                                             BaseLocalization.notification_text_queue_update,
                                                             item_type, step, value)

    async def handle_entry(self, item_type, value):
        def key_gen(s):
            return f'q:{item_type}:{s}'

        k_free = key_gen('free')
        k_packed = key_gen('packed')

        cdt = self.cooldown_tracker
        free_notified_recently = not (await cdt.can_do(k_free, self.cooldown))
        packed_notified_recently = not (await cdt.can_do(k_packed, self.cooldown))

        if value > self.threshold:
            if not packed_notified_recently:
                await cdt.clear(k_free)
                await cdt.do(k_packed)
                await self.notify(item_type, self.threshold, value)
        elif value == 0:
            if not free_notified_recently and packed_notified_recently:
                await cdt.clear(k_packed)
                await cdt.do(k_free)
                await self.notify(item_type, 0, 0)

    async def on_data(self, sender, data: QueueInfo):
        self.logger.info(f"got queue: {data}")
        await self.time_series.add(swap=data.swap, outbound=data.outbound)
        await self.handle_entry('swap', data.swap)
        await self.handle_entry('outbound', data.outbound)
