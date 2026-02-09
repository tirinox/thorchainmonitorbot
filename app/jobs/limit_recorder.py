from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.runepool import AlertPOLState


class LimitSwapStatsRecorder(WithLogger, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, event):
        ...
