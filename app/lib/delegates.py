import logging
import time
from abc import ABC, abstractmethod

from lib.flagship import Flagship


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
        if not delegate:
            raise ValueError("Delegate is None")
        if delegate is self:
            raise ValueError("Cannot add self as delegate")
        if delegate not in self.delegates:
            self.delegates.append(delegate)
        return self

    async def handle_error(self, e, sender=None):
        sender = sender or self
        for delegate in self.delegates:
            await delegate.on_error(sender, e)

    async def pass_data_to_listeners(self, data, sender=None):
        if not data:
            return None
        sender = sender or self

        summary = {}

        for delegate in self.delegates:
            if not await self.is_passage_allowed(delegate):
                logging.warning(f"Passage not allowed to delegate {delegate}")
                continue

            delegate: INotified
            t0 = time.monotonic()

            try:
                await delegate.on_data(sender, data)
            except Exception as e:
                logging.exception(f"{e!r}")

            t1 = time.monotonic()
            summary[str(delegate)] = t1 - t0

        return summary

    @property
    def my_class_name(self):
        return self.__class__.__name__

    async def is_passage_allowed(self, sender=None):
        if flagship := self.maybe_get_flagship():
            flag_name = f"pass:{self.my_class_name}:{sender.__class__.__name__}"
            if not await flagship.is_flag_set(flag_name):
                return False
        return True

    def maybe_get_flagship(self) -> Flagship | None:
        if hasattr(self, 'deps'):
            d = getattr(self, 'deps')
            return d.flagship
        return None
