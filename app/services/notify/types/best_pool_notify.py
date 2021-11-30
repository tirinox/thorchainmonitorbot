from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger


class BestPoolsNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

    async def on_data(self, sender, data):
        pass

