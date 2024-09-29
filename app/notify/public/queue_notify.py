from comm.dialog.picture.queue_picture import QUEUE_TIME_SERIES

from jobs.fetch.queue import QueueInfo
from lib.cooldown import CooldownBiTrigger
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.queue import AlertQueue
from models.time_series import TimeSeries


class QueueNotifier(INotified, WithLogger, WithDelegates):
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
        self.ts = TimeSeries(QUEUE_TIME_SERIES, self.deps.db, self.MAX_POINTS)

        self.logger.debug(f'Queue alert config: {deps.cfg.queue}')

    async def handle_entry(self, item_type, ts: TimeSeries):
        avg_value = await ts.average(self.avg_period, item_type)

        if avg_value is None:
            return

        self.logger.info(f'Avg queue {item_type} is {avg_value:.1f}')

        cd_trigger = CooldownBiTrigger(self.deps.db, f'QueueClog:{item_type}', self.cooldown, self.cooldown)

        if avg_value > self.threshold_congested:
            if await cd_trigger.turn_on():
                await self.pass_data_to_listeners(AlertQueue(
                    item_type, is_free=False, value=int(avg_value)
                ))
        elif avg_value < self.threshold_free:
            if await cd_trigger.turn_off():
                await self.pass_data_to_listeners(AlertQueue(
                    item_type, is_free=True, value=int(avg_value)
                ))

    async def store_queue_info(self, data: QueueInfo):
        await self.ts.add(swap=data.swap,
                          outbound=data.outbound,
                          internal=data.internal)

    async def on_data(self, sender: 'QueueStoreMetrics', data: QueueInfo):
        for key in self.watch_queues:
            await self.handle_entry(key, sender.ts)

        # await self.ts.trim_oldest(self.MAX_POINTS)


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
