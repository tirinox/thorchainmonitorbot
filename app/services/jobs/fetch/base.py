import asyncio
import logging
from abc import ABC, abstractmethod

from services.lib.depcont import DepContainer


class INotified(ABC):
    @abstractmethod
    async def on_data(self, sender, data): ...

    async def on_error(self, sender, e):
        ...


class WithDelegates:
    def __init__(self):
        self.delegates = set()

    def subscribe(self, delegate: INotified):
        self.delegates.add(delegate)
        return self

    async def handle_error(self, e, sender=None):
        sender = sender or self
        for delegate in self.delegates:
            await delegate.on_error(sender, e)

    async def handle_data(self, data, sender=None):
        if not data:
            return
        sender = sender or self
        for delegate in self.delegates:
            delegate: INotified
            await delegate.on_data(sender, data)


class BaseFetcher(WithDelegates, ABC):
    def __init__(self, deps: DepContainer, sleep_period=60):
        super().__init__()
        self.deps = deps
        self.name = self.__class__.__qualname__
        self.sleep_period = sleep_period
        self.logger = logging.getLogger(f'{self.__class__.__name__}')
        self.delegates = set()

    async def post_action(self, data):
        ...

    @abstractmethod
    async def fetch(self):
        ...

    async def run(self):
        await asyncio.sleep(1)
        while True:
            try:
                data = await self.fetch()
                await self.handle_data(data)
                await self.post_action(data)
            except Exception as e:
                self.logger.exception(f"task error: {e}")

                try:
                    await self.handle_error(e)
                except Exception as e:
                    self.logger.exception(f"task error while handling on_error: {e}")

            await asyncio.sleep(self.sleep_period)
