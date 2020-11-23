import logging

from localization import BaseLocalization
from services.fetch.base import INotified
from services.fetch.queue import QueueInfo
from services.lib.cooldown import CooldownTracker
from services.lib.depcont import DepContainer
from services.models.time_series import PriceTimeSeries

QUEUE_STREAM = 'QUEUE'


class QueueNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger('QueueNotifier')
        self.cooldown_tracker = CooldownTracker(deps.db)
        self.cooldown = deps.cfg.queue.cooldown
        self.threshold = deps.cfg.queue.steps[0]
        self.logger.info(f'config: {deps.cfg.queue}')
        self.steps = tuple(map(int, deps.cfg.queue.steps))

        self.time_series = PriceTimeSeries(QUEUE_STREAM, deps.db)

    async def notify(self, item_type, step, value):
        await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
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
