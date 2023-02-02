import asyncio
import json

from aioredis import Redis

from services.lib.date_utils import now_ts
from services.lib.delegates import WithDelegates
from services.lib.utils import WithLogger


class Scheduler(WithLogger, WithDelegates):
    def __init__(self, r: Redis, name, poll_interval: float = 10):
        assert name
        super().__init__()
        self.name = name
        self._poll_interval = poll_interval
        self._r = r
        self._running = False

    async def schedule(self, timestamp, data):
        now = now_ts()
        if timestamp < now:
            self.logger.warning(f'Scheduling: {self.name} at {timestamp} (before now!)')
            return

        self.logger.debug(f'Scheduling: {self.name} at {timestamp} ({timestamp - now} seconds from now)')

        data_raw = json.dumps(data)
        await self._r.zadd(self.key(), {data_raw: timestamp})

    async def _run_handler(self, name, ev):
        try:
            delay = now_ts() - ev[1]
            self.logger.debug(f'Running scheduler handler: {name}, delay: {delay:.3f} sec')
            data = json.loads(ev[0])
            await self.pass_data_to_listeners(data)
            self.logger.debug(f'Finished scheduler handler: {name}')
        except Exception as e:
            self.logger.exception(f'Error in scheduler handler: {e}', stack_info=True)

    async def awaiting_events(self):
        return await self._r.zrange(self.key(), 0, -1, withscores=True)

    async def _process(self):
        now = now_ts()
        evs = await self._r.zrangebyscore(self.key(), 0, now, withscores=True)
        await self._r.zremrangebyscore(self.key(), 0, now)
        for ev in evs:
            await self._run_handler(self.name, ev)

    def key(self):
        return f'Scheduler:{self.name}'

    async def clear(self, name):
        await self._r.delete(self.key())

    async def run(self):
        if self._running:
            self.logger.warning('Scheduler already running!')
            return

        self._running = True
        while self._running:
            await asyncio.sleep(self._poll_interval)
            try:
                await self._process()
            except Exception as e:
                self.logger.exception(f'Error in scheduler: {e}', stack_info=True)
