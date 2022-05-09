import asyncio
from abc import ABC, abstractmethod

from services.lib.depcont import DepContainer
from services.lib.utils import class_logger


class INotified(ABC):
    @abstractmethod
    async def on_data(self, sender, data): ...

    async def on_error(self, sender, e):
        ...


class WithDelegates:
    def __init__(self):
        self.delegates = []  # list for fixed order

    def subscribe(self, delegate: INotified):
        if delegate not in self.delegates:
            self.delegates.append(delegate)
        return self

    async def handle_error(self, e, sender=None):
        sender = sender or self
        for delegate in self.delegates:
            await delegate.on_error(sender, e)

    async def pass_data_to_listeners(self, data, sender=None):
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
        self.logger = class_logger(self)

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
                await self.pass_data_to_listeners(data)
                await self.post_action(data)
            except Exception as e:
                self.logger.exception(f"task error: {e}")

                try:
                    await self.handle_error(e)
                except Exception as e:
                    self.logger.exception(f"task error while handling on_error: {e}")

            await asyncio.sleep(self.sleep_period)
