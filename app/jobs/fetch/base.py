import asyncio
import datetime
import json
import random
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Dict

from redis import BusyLoadingError

from lib.date_utils import now_ts, MINUTE
from lib.db import DB
from lib.delegates import WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger

UNPAUSE_AFTER = 5 * MINUTE


# UNPAUSE_AFTER = 30


class WatchedEntity:
    def __init__(self):
        super().__init__()
        self.name = self.__class__.__qualname__
        self.sleep_period = 1.0
        self.initial_sleep = 1.0
        self.last_timestamp = 0.0
        self.error_counter = 0
        self.total_ticks = 0
        self.creating_date = now_ts()

    @property
    def success_rate(self):
        if not self.total_ticks:
            return 100.0
        return (self.total_ticks - self.error_counter) / self.total_ticks * 100.0


def qualname(obj):
    if hasattr(obj, '__qualname__'):
        return obj.__qualname__
    return obj.__class__.__qualname__


class DataController(WithLogger):
    def __init__(self):
        super().__init__()
        self._tracker = {}
        self._all_paused = False

    @property
    def all_paused(self):
        return self._all_paused

    def request_global_pause(self):
        self.logger.warning('Global pause requested!')
        self._all_paused = True

    def request_global_resume(self):
        self.logger.warning('Global resume requested!')
        self._all_paused = False

    def register(self, entity: WatchedEntity):
        if not entity:
            return
        name = entity.name
        self._tracker[name] = entity
        self.logger.info(f'Registered: {entity} ({id(entity)})')

    def unregister(self, entity):
        if not entity:
            return
        self._tracker.pop(entity.name)

    @property
    def summary(self) -> Dict[str, WatchedEntity]:
        return self._tracker

    DB_KEY = 'DataController:FetcherStats'

    async def save_stats(self, db: DB):
        v: BaseFetcher
        data = {
            'all_paused': self._all_paused,
            'trackers': [{
                'name': k,
                'error_counter': v.error_counter,
                'total_ticks': v.total_ticks,
                'last_timestamp': v.last_timestamp,
                'success_rate': v.success_rate,
                'last_run_time': v.dbg_last_run_time,
                'avg_run_time': v.dbg_average_run_time,
                'sleep_period': v.sleep_period,
            } for k, v in self._tracker.items()],
        }
        self.logger.info(f'Saving stats of {len(data["trackers"])} fetchers')
        await db.redis.set(self.DB_KEY, json.dumps(data))

    async def load_stats(self, db: DB):
        data = await db.redis.get(self.DB_KEY)
        if not data:
            return
        return json.loads(data)

    async def run_save_job(self, db: DB, interval=20):
        while True:
            try:
                await self.save_stats(db)
            except Exception as e:
                self.logger.exception(f'Error while saving stats: {e!r}')
            await asyncio.sleep(interval)


class BaseFetcher(WithDelegates, WatchedEntity, ABC, WithLogger):
    MAX_STARTUP_DELAY = 20

    def __init__(self, deps: DepContainer, sleep_period=66):
        super().__init__()
        self.deps = deps

        self.sleep_period = sleep_period
        self.initial_sleep = random.uniform(0, min(self.MAX_STARTUP_DELAY, sleep_period))
        if sleep_period > 0:
            self.data_controller.register(self)
        self.run_times = deque(maxlen=100)

    @property
    def dbg_last_run_time(self):
        return self.run_times[-1] if self.run_times else None

    @property
    def dbg_average_run_time(self):
        return sum(self.run_times) / len(self.run_times) if self.run_times else None

    @property
    def data_controller(self):
        if not self.deps.data_controller:
            self.deps.data_controller = DataController()
        return self.deps.data_controller

    async def post_action(self, data):
        ...

    @abstractmethod
    async def fetch(self):
        ...

    async def run_once(self):
        self.logger.info(f'Tick #{self.total_ticks}')
        if self.data_controller.all_paused:
            self.logger.warning('Global pause')
            return

        t0 = time.monotonic()
        try:
            data = await self.fetch()
            await self.pass_data_to_listeners(data)
            await self.post_action(data)
        except Exception as e:
            # If the database is in a busy state, we need to pause for a while
            if isinstance(e, BusyLoadingError):
                await self._handle_db_busy_error(e)

            self.logger.exception(f"task error: {e}")
            self.error_counter += 1
            try:
                await self.handle_error(e)
            except Exception as e:
                self.logger.exception(f"task error while handling on_error: {e}")
        finally:
            self.total_ticks += 1
            self.last_timestamp = datetime.datetime.now().timestamp()
            delta = time.monotonic() - t0
            self.run_times.append(delta)

    async def _handle_db_busy_error(self, e):
        self.deps.emergency.report(self.name, f'BusyLoadingError: {e}')
        self.data_controller.request_global_pause()
        # noinspection PyAsyncCall
        asyncio.create_task(self._unpause_after())

    async def _unpause_after(self):
        await asyncio.sleep(UNPAUSE_AFTER)
        self.data_controller.request_global_resume()

    async def _run(self):
        if self.sleep_period < 0:
            self.logger.info('This fetcher is disabled.')
            return

        self.logger.info(f'Waiting {self.initial_sleep:.1f} sec before starting this fetcher...')
        await asyncio.sleep(self.initial_sleep)
        self.logger.info(f'Starting this fetcher with period {self.sleep_period:.1f} sec.')

        while True:
            await self.run_once()
            await asyncio.sleep(self.sleep_period)

    async def run(self):
        try:
            await self._run()
        except Exception as e:
            self.logger.error(f'Unexpected termination due to exception {e!r}')
        finally:
            self.logger.warning('Unexpected termination!')

    def run_in_background(self):
        return asyncio.create_task(self.run())


class PeriodicTask(BaseFetcher):
    async def fetch(self):
        # Does nothing, just a placeholder for periodic tasks
        return True
