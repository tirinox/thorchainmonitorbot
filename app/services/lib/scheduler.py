import asyncio

from aioredis import Redis

from services.lib.date_utils import now_ts, DAY
from services.lib.delegates import WithDelegates
from services.lib.utils import WithLogger


class Scheduler(WithLogger, WithDelegates):
    def __init__(self, r: Redis, name, poll_interval: float = 10, forget_after=DAY):
        assert name
        super().__init__()
        self.name = name
        self._poll_interval = poll_interval
        self._r = r
        self._running = False
        self.forget_after = forget_after

    async def schedule(self, ident, timestamp=0.0, period=0.0):
        assert isinstance(ident, (str, int, float)) and ident, 'ident must be a string or number'

        ev_desc = self.ev_desc(ident)
        now = now_ts()
        if not timestamp:
            timestamp = now
        elif timestamp < now:
            self.logger.warning(f'Scheduling: {ev_desc} at {timestamp} (before now!)')
            return

        self.logger.debug(f'Scheduling: {ev_desc} at {timestamp} ({timestamp - now} seconds from now)')

        await self._r.zadd(self.key_timeline(), {ident: timestamp})

        key_period = self.key_period(ident)
        if period > 0:
            await self._r.set(key_period, period)
        else:
            await self._r.delete(key_period)

    def ev_desc(self, ident):
        return f'"{self.name}:{ident}"'

    async def get_period(self, ident):
        return await self._r.get(self.key_period(ident))

    async def get_next_timestamp(self, ident):
        score = await self._r.zscore(self.key_timeline(), ident)
        return float(score) if score else None

    async def _run_handler(self, ev):
        try:
            now = now_ts()
            delay = now - ev[1]
            ident = ev[0]
            ev_desc = self.ev_desc(ident)

            if 0 < self.forget_after < delay:
                self.logger.info(f'Event seems forgotten: {ev_desc}. Ignoring.')
                return

            self.logger.debug(f'Running scheduler handler: {ev_desc}, delay: {delay:.3f} sec')

            period = await self.get_period(ident)
            if period:
                try:
                    period = float(period)
                    if period > 0:
                        await self.schedule(ident, now + period, period)
                    elif period < 0:
                        self.logger.info(f'Periodic event seems cancelled: {ev_desc}. Ignoring.')
                        return
                except ValueError:
                    self.logger.warning(f'Invalid period: {period}. Failed to reschedule: {ev_desc}')

            await self.pass_data_to_listeners(ident)
            self.logger.debug(f'Finished scheduler handler: {ev_desc}')

        except Exception as e:
            self.logger.exception(f'Error in scheduler handler: {e}', stack_info=True)

    async def awaiting_events(self):
        return await self._r.zrange(self.key_timeline(), 0, -1, withscores=True)

    async def all_periodic_events(self, ident=None):
        return await self._r.keys(self.key_period(ident or '*'))

    async def cancel(self, ident):
        await self._r.zrem(self.key_timeline(), ident)
        await self._r.delete(self.key_period(ident))
        self.logger.debug(f'Cancelled: {self.ev_desc(ident)}')

    async def cancel_all_periodic(self, ident=None):
        keys = await self.all_periodic_events(ident)
        if keys:
            await self._r.delete(*keys)
            await self._r.zrem(self.key_timeline(), *keys)

    async def _process(self):
        now = now_ts()
        key_timeline = self.key_timeline()
        evs = await self._r.zrangebyscore(key_timeline, 0, now, withscores=True)
        await self._r.zremrangebyscore(key_timeline, 0, now)
        for ev in evs:
            await self._run_handler(ev)

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
