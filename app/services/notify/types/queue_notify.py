import logging

from localization import BaseLocalization
from services.dialog.picture.queue_picture import queue_graph, QUEUE_TIME_SERIES
from services.jobs.fetch.base import INotified
from services.jobs.fetch.queue import QueueInfo
from services.lib.cooldown import CooldownBiTrigger
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.texts import BoardMessage
from services.lib.utils import class_logger
from services.models.time_series import TimeSeries


class QueueNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

        cfg = deps.cfg.queue
        self.cooldown = parse_timespan_to_seconds(cfg.cooldown)
        self.threshold_congested = int(cfg.threshold.congested)
        self.threshold_free = int(cfg.threshold.free)
        self.avg_period = parse_timespan_to_seconds(cfg.threshold.avg_period)

        self.logger.info(f'config: {deps.cfg.queue}')

    async def notify(self, item_type, step, value, with_picture=True):
        user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)

        if with_picture:
            photo = await queue_graph(self.deps, self.deps.loc_man.default)
        else:
            photo = None

        async def message_gen(chat_id):
            loc: BaseLocalization = user_lang_map[chat_id]
            text = loc.notification_text_queue_update(item_type, step, value)
            if photo is not None:
                return BoardMessage.make_photo(photo, text)
            else:
                return text

        await self.deps.broadcaster.broadcast(user_lang_map.keys(), message_gen)

    async def handle_entry(self, item_type, ts: TimeSeries):
        avg_value = await ts.average(self.avg_period, item_type)
        if avg_value is None:
            return

        self.logger.info(f'Avg {item_type} is {avg_value:.1f}')

        cd_trigger = CooldownBiTrigger(self.deps.db, f'QueueClog-{item_type}', self.cooldown, self.cooldown)

        if avg_value > self.threshold_congested:
            if await cd_trigger.turn_on():
                await self.notify(item_type, self.threshold_congested, int(avg_value))
        elif avg_value < self.threshold_free:
            if await cd_trigger.turn_off():
                await self.notify(item_type, 0, 0)

    async def on_data(self, sender, data: QueueInfo):
        self.logger.info(f"got queue: {data}")

        ts = TimeSeries(QUEUE_TIME_SERIES, self.deps.db)
        await ts.add(swap=data.swap,
                     outbound=data.outbound,
                     internal=data.internal)
        self.deps.queue_holder = data

        for key in ('outbound', 'internal', 'swap'):
            await self.handle_entry(key, ts)
