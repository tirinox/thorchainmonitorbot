import asyncio
import logging
from abc import ABC, abstractmethod

from services.lib.depcont import DepContainer


class INotified(ABC):
    @abstractmethod
    async def on_data(self, sender, data): ...

    async def on_error(self, sender, e):
        ...


class BaseFetcher(ABC):
    def __init__(self, deps: DepContainer, sleep_period=60):
        self.deps = deps
        self.name = self.__class__.__qualname__
        self.sleep_period = sleep_period
        self.logger = logging.getLogger(f'{self.__class__.__name__}')
        self.delegates = set()

    def subscribe(self, delegate: INotified):
        self.delegates.add(delegate)
        return self

    @abstractmethod
    async def fetch(self):
        ...

    async def handle_error(self, e):
        for delegate in self.delegates:
            await delegate.on_error(self, e)

    async def run(self):
        await asyncio.sleep(1)
        while True:
            try:
                data = await self.fetch()
                if data:
                    for delegate in self.delegates:
                        delegate: INotified
                        await delegate.on_data(self, data)

            except Exception as e:
                self.logger.exception(f"task error: {e}")

                try:
                    await self.handle_error(e)
                except Exception as e:
                    self.logger.exception(f"task error while handling on_error: {e}")

            await asyncio.sleep(self.sleep_period)
