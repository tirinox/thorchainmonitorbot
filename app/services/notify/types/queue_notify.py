import logging

from localization import BaseLocalization
from services.dialog.queue_picture import queue_graph, QUEUE_TIME_SERIES
from services.fetch.base import INotified
from services.fetch.queue import QueueInfo
from services.lib.cooldown import CooldownSingle, Cooldown
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.texts import BoardMessage
from services.models.time_series import TimeSeries


class QueueNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger('QueueNotifier')
        self.cooldown_tracker = CooldownSingle(deps.db)
        self.cooldown_for_graph = Cooldown(deps.db, 'queue_graph', parse_timespan_to_seconds('1h'), 2)

        self.cooldown = parse_timespan_to_seconds(deps.cfg.queue.cooldown)
        self.threshold = deps.cfg.queue.steps[0]
        self.logger.info(f'config: {deps.cfg.queue}')
        self.steps = tuple(map(int, deps.cfg.queue.steps))

    async def notify(self, item_type, step, value, with_picture=True):
        user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)

        if with_picture:
            photo = await queue_graph(self.deps, self.deps.loc_man.default)
        else:
            photo = None

        async def message_gen(chat_id):
            loc: BaseLocalization = user_lang_map[chat_id]
            text = loc.notification_text_queue_update(item_type, step, value)
            if with_picture:
                return BoardMessage.make_photo(photo, text)
            else:
                return text

        await self.deps.broadcaster.broadcast(user_lang_map.keys(), message_gen)

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
                # if 3 times per last 2 hours -> show graph

    async def on_data(self, sender, data: QueueInfo):
        self.logger.info(f"got queue: {data}")

        ts = TimeSeries(QUEUE_TIME_SERIES, self.deps.db)
        await ts.add(swap_queue=data.swap, outbound_queue=data.outbound)
        self.deps.queue_holder = data

        await self.handle_entry('swap', data.swap)
        await self.handle_entry('outbound', data.outbound)
