import asyncio
from abc import ABC, abstractmethod

from services.lib.delegates import WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger


class BaseFetcher(WithDelegates, ABC):
    def __init__(self, deps: DepContainer, sleep_period=60):
        super().__init__()
        self.deps = deps
        self.name = self.__class__.__qualname__
        self.sleep_period = sleep_period
        self.initial_sleep = 1.0
        self.logger = class_logger(self)

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
            try:
                await self.handle_error(e)
            except Exception as e:
                self.logger.exception(f"task error while handling on_error: {e}")

    async def run(self):
        if self.sleep_period < 0:
            self.logger.info('This fetcher is disabled.')
            return

        await asyncio.sleep(self.initial_sleep)
        while True:
            await self.run_once()
            await asyncio.sleep(self.sleep_period)
