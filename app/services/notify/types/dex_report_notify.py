from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class DexReportNotifier(INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cd = parse_timespan_to_seconds(deps.cfg.dex_report.notification.cooldown)
        self.spam_cd = Cooldown(self.deps.db, 'DexReport', cd)

    async def on_data(self, sender, data):
        pass
