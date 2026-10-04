import asyncio
import math
import random

from redis.asyncio import Redis

from lib.date_utils import now_ts, DAY, MINUTE
from lib.delegates import WithDelegates
from lib.logs import WithLogger


class PrivateScheduler(WithLogger, WithDelegates):
    def __init__(self, r: Redis, name, poll_interval: float = 10, forget_after=DAY, catch_up_spread=30 * MINUTE):
        assert name
        super().__init__()
        self.name = name
        self._poll_interval = poll_interval
        self._r = r
        self._running = False
        # one-shot events that are late more than this are dropped; periodic events are never dropped
        self.forget_after = forget_after
        # periodic events that are late more than this (e.g. after a downtime) fire once
        # at a random moment within this window, so they don't all hit the APIs at once
        self.catch_up_spread = max(catch_up_spread, 2 * poll_interval)
        # optional async predicate(ident) -> bool: which lost periodic events to bring back on start
        self.should_restore = None
        self.emergency = None  # EmergencyReport, set by the wiring

    async def schedule(self, ident, timestamp=0.0, period=0.0):
        assert isinstance(ident, (str, int, float)) and ident, 'ident must be a string or number'

        ev_desc = self.ev_desc(ident)
        now = now_ts()
        if not timestamp:
            timestamp = now + period
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

    @staticmethod
    def next_slot(ev_ts, now, period):
        # the first moment strictly after now that keeps the phase of the event, missed slots are skipped
        return ev_ts + (math.floor((now - ev_ts) / period) + 1) * period

    def _report_emergency(self, message, **kwargs):
        if self.emergency:
            self.emergency.report(f'PrivateScheduler:{self.name}', message, **kwargs)

    async def _run_handler(self, ev):
        try:
            now = now_ts()
            ident, ev_ts = ev
            delay = now - ev_ts
            ev_desc = self.ev_desc(ident)
            key_timeline = self.key_timeline()

            raw_period = await self.get_period(ident)
            try:
                period = float(raw_period) if raw_period else 0.0
            except ValueError:
                self.logger.warning(f'Invalid period: {raw_period}. Failed to reschedule: {ev_desc}')
                period = 0.0

            if period < 0:
                self.logger.info(f'Periodic event seems cancelled: {ev_desc}. Ignoring.')
                await self._r.zrem(key_timeline, ident)
                return

            if period > 0:
                # the event is moved forward instead of being removed, so it is never lost;
                # xx=True: do not resurrect an event cancelled in the meantime
                if delay > self.catch_up_spread:
                    catch_up_ts = now + random.uniform(0, self.catch_up_spread)
                    self.logger.info(f'Periodic event {ev_desc} is late by {delay:.0f} sec. '
                                     f'Catching up in {catch_up_ts - now:.0f} sec.')
                    await self._r.zadd(key_timeline, {ident: catch_up_ts}, xx=True)
                    return
                await self._r.zadd(key_timeline, {ident: self.next_slot(ev_ts, now, period)}, xx=True)
            else:
                await self._r.zrem(key_timeline, ident)
                if 0 < self.forget_after < delay:
                    self.logger.info(f'Event seems forgotten: {ev_desc}. Ignoring.')
                    return

            self.logger.debug(f'Running scheduler handler: {ev_desc}, delay: {delay:.3f} sec')
            await self.pass_data_to_listeners(ident)
            self.logger.debug(f'Finished scheduler handler: {ev_desc}')

        except Exception as e:
            self.logger.exception(f'Error in scheduler handler: {e}', stack_info=True)
            self._report_emergency('Scheduler handler failed', event=repr(ev), error=repr(e))

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
        # events stay in the timeline until the handler moves or removes them one by one
        evs = await self._r.zrangebyscore(key_timeline, 0, now, withscores=True)
        for ev in evs:
            await self._run_handler(ev)

    def key_timeline(self):
        return f'Scheduler:{self.name}:TimeLine'

    def key_period(self, ident):
        return f'Scheduler:{self.name}:Period:{ident}'

    async def clear(self):
        await self._r.delete(self.key_timeline())

    async def restore_lost_periodic(self):
        """
        Older versions dropped periodic events that were late more than forget_after, but kept their period keys.
        Such events are put back into the timeline, spread like catch-up events.
        """
        key_timeline = self.key_timeline()
        prefix = self.key_period('')
        restored, skipped = [], 0
        for key in await self.all_periodic_events():
            ident = key[len(prefix):]
            try:
                raw_period = await self._r.get(key)
                if not raw_period or float(raw_period) <= 0:
                    continue
                if await self._r.zscore(key_timeline, ident) is not None:
                    continue
                if self.should_restore and not await self.should_restore(ident):
                    skipped += 1
                    continue
                # nx=True: never move an event that was scheduled in the meantime
                ts = now_ts() + random.uniform(0, self.catch_up_spread)
                if await self._r.zadd(key_timeline, {ident: ts}, nx=True):
                    restored.append(ident)
            except Exception as e:
                self.logger.exception(f'Failed to restore {self.ev_desc(ident)}: {e}')

        if restored or skipped:
            self.logger.warning(f'Restored {len(restored)} lost periodic events of "{self.name}", '
                                f'skipped {skipped}.')
        return restored

    async def run(self):
        if self._running:
            self.logger.warning('Scheduler already running!')
            return

        self._running = True
        try:
            await self.restore_lost_periodic()
        except Exception as e:
            self.logger.exception(f'Failed to restore lost periodic events: {e}')

        while self._running:
            await asyncio.sleep(self._poll_interval)
            try:
                await self._process()
            except Exception as e:
                self.logger.exception(f'Error in scheduler: {e}', stack_info=True)
                self._report_emergency('Scheduler loop failed', error=repr(e))

    def run_in_background(self):
        return asyncio.create_task(self.run())
