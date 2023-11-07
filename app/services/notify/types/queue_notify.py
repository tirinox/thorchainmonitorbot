from localization.manager import BaseLocalization
from services.dialog.picture.queue_picture import queue_graph, QUEUE_TIME_SERIES
from services.jobs.fetch.queue import QueueInfo
from services.lib.cooldown import CooldownBiTrigger
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.time_series import TimeSeries
from services.notify.channel import BoardMessage


class QueueNotifier(INotified, WithLogger):
    DEFAULT_WATCH_QUEUES = ('outbound', 'internal', 'swap')
    MAX_POINTS = 200_000

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        cfg = deps.cfg.queue
        self.cooldown = parse_timespan_to_seconds(cfg.cooldown)
        self.threshold_congested = int(cfg.threshold.congested)
        self.threshold_free = int(cfg.threshold.free)
        self.avg_period = parse_timespan_to_seconds(cfg.threshold.avg_period)
        self.watch_queues = cfg.get('watch_queues', self.DEFAULT_WATCH_QUEUES)
        self.ts = TimeSeries(QUEUE_TIME_SERIES, self.deps.db)

        self.logger.info(f'config: {deps.cfg.queue}')

    async def notify(self, item_type, is_free, value, with_picture=True):
        photo_name = ''
        if with_picture:
            photo, photo_name = await queue_graph(self.deps, self.deps.loc_man.default)
        else:
            photo = None

        async def message_gen(loc: BaseLocalization):
            text = loc.notification_text_queue_update(item_type, is_free, value)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.notify_preconfigured_channels(message_gen)

    async def handle_entry(self, item_type, ts: TimeSeries):
        avg_value = await ts.average(self.avg_period, item_type)

        # # fixme: debug
        # if item_type == 'outbound':
        #     avg_value = 1.2
        # # fixme: debug

        if avg_value is None:
            return

        self.logger.info(f'Avg queue {item_type} is {avg_value:.1f}')

        cd_trigger = CooldownBiTrigger(self.deps.db, f'QueueClog:{item_type}', self.cooldown, self.cooldown)

        if avg_value > self.threshold_congested:
            if await cd_trigger.turn_on():
                await self.notify(item_type, is_free=False, value=int(avg_value))
        elif avg_value < self.threshold_free:
            if await cd_trigger.turn_off():
                await self.notify(item_type, is_free=True, value=avg_value)

    async def store_queue_info(self, data: QueueInfo):
        await self.ts.add(swap=data.swap,
                          outbound=data.outbound,
                          internal=data.internal)

    async def on_data(self, sender: 'QueueStoreMetrics', data: QueueInfo):
        for key in self.watch_queues:
            await self.handle_entry(key, sender.ts)

        await self.ts.trim_oldest(self.MAX_POINTS)


class QueueStoreMetrics(INotified, WithDelegates):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.ts = TimeSeries(QUEUE_TIME_SERIES, deps.db)

    async def store_queue_info(self, data: QueueInfo):
        self.deps.queue_holder = data

        await self.ts.add(swap=data.swap,
                          outbound=data.outbound,
                          internal=data.internal)

    async def on_data(self, sender, data):
        await self.store_queue_info(data)
        await self.pass_data_to_listeners(data, self)
