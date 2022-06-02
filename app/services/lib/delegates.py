from abc import ABC, abstractmethod


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