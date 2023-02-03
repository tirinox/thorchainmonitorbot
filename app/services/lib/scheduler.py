import asyncio

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

    async def schedule(self, ident, timestamp=0, period=0.0):
        assert isinstance(ident, (str, int, float)) and ident, 'ident must be a string or number'

        now = now_ts()
        if not timestamp:
            timestamp = now
        elif timestamp < now:
            self.logger.warning(f'Scheduling: {self.name}:{ident} at {timestamp} (before now!)')
            return

        self.logger.debug(f'Scheduling: {self.name}:{ident} at {timestamp} ({timestamp - now} seconds from now)')

        await self._r.zadd(self.key_timeline(), {ident: timestamp})

        key_period = self.key_period(ident)
        if period > 0:
            await self._r.set(key_period, period)
        else:
            await self._r.delete(key_period)

    async def _run_handler(self, name, ev):
        try:
            now = now_ts()
            delay = now - ev[1]
            self.logger.debug(f'Running scheduler handler: {name}, delay: {delay:.3f} sec')
            ident = ev[0]
            await self.pass_data_to_listeners(ident)
            self.logger.debug(f'Finished scheduler handler: {name}')

            period = await self._r.get(self.key_period(ident))
            if period:
                try:
                    period = float(period)
                    if period > 0:
                        await self.schedule(ident, now + period, period)
                except ValueError:
                    self.logger.warning(f'Invalid period: {period}. Failed to reschedule: {name}:{ident}')

        except Exception as e:
            self.logger.exception(f'Error in scheduler handler: {e}', stack_info=True)

    async def awaiting_events(self):
        return await self._r.zrange(self.key_timeline(), 0, -1, withscores=True)

    async def all_periodic_events(self):
        return await self._r.keys(self.key_period('*'))

    async def cancel(self, ident):
        await self._r.zrem(self.key_timeline(), ident)
        await self._r.delete(self.key_period(ident))

    async def cancel_all_periodic(self):
        for key in await self.all_periodic_events():
            await self._r.delete(key)

    async def _process(self):
        now = now_ts()
        key_timeline = self.key_timeline()
        evs = await self._r.zrangebyscore(key_timeline, 0, now, withscores=True)
        await self._r.zremrangebyscore(key_timeline, 0, now)
        for ev in evs:
            await self._run_handler(self.name, ev)

    def key_timeline(self):
        return f'Scheduler:{self.name}:TimeLine'

    def key_period(self, ident):
        return f'Scheduler:{self.name}:Period:{ident}'

    async def clear(self):
        await self._r.delete(self.key_timeline())

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
