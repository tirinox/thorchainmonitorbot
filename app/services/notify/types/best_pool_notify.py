from services.jobs.fetch.base import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger


class BestPoolsNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        cooldown = parse_timespan_to_seconds(deps.cfg.as_str('best_pools.cooldown', '5h'))
        self.cooldown = Cooldown(self.deps.db, 'BestPools', cooldown)

    async def _write_previous_data(self):
        ...

    async def _get_previous_data(self):
        ...

    async def on_data(self, sender, data):
        pass

