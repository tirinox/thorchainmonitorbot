from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class PersonalPeriodicNotificationService(WithLogger, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, data):
        pass  # todo: implement
