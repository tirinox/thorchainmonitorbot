import logging
import time
from abc import ABC, abstractmethod


class INotified(ABC):
    @abstractmethod
    async def on_data(self, sender, data): ...

    async def on_error(self, sender, e):
        ...


class WithDelegates:
    def __init__(self):
        super().__init__()
        self.delegates = []  # list for fixed order

    def add_subscriber(self, delegate: INotified):
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

        summary = {}

        for delegate in self.delegates:
            delegate: INotified
            t0 = time.monotonic()
            try:
                await delegate.on_data(sender, data)
            except Exception as e:
                logging.exception(f"{e!r}")
            t1 = time.monotonic()
            summary[str(delegate)] = t1 - t0

        return summary
