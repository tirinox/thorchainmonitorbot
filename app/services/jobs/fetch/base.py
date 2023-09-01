import asyncio
import datetime
from abc import ABC, abstractmethod
from typing import Dict

from services.lib.date_utils import now_ts
from services.lib.delegates import WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger


class DataController:
    def __init__(self):
        self._tracker = {}

    def register(self, fetcher):
        if not fetcher:
            return
        name = fetcher.name
        self._tracker[name] = fetcher

    def unregister(self, fetcher):
        if not fetcher:
            return
        self._tracker.pop(fetcher.name)

    @property
    def summary(self) -> Dict[str, 'BaseFetcher']:
        return self._tracker


class BaseFetcher(WithDelegates, ABC):
    def __init__(self, deps: DepContainer, sleep_period=60):
        super().__init__()
        self.deps = deps
        self.name = self.__class__.__qualname__
        self.sleep_period = sleep_period
        self.initial_sleep = 1.0
        self.logger = class_logger(self)
        self.last_timestamp = 0.0
        self.error_counter = 0
        self.total_ticks = 0
        self.data_controller.register(self)
        self.creating_date = now_ts()

    @property
    def success_rate(self):
        if not self.total_ticks:
            return 100.0
        return (self.total_ticks - self.error_counter) / self.total_ticks * 100.0

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
        try:
            data = await self.fetch()
            await self.pass_data_to_listeners(data)
            await self.post_action(data)
        except Exception as e:
            self.logger.exception(f"task error: {e}")
            self.error_counter += 1
            try:
                await self.handle_error(e)
            except Exception as e:
                self.logger.exception(f"task error while handling on_error: {e}")
        finally:
            self.total_ticks += 1
            self.last_timestamp = datetime.datetime.now().timestamp()

    async def run(self):
        if self.sleep_period < 0:
            self.logger.info('This fetcher is disabled.')
            return

        await asyncio.sleep(self.initial_sleep)
        while True:
            await self.run_once()
            await asyncio.sleep(self.sleep_period)
