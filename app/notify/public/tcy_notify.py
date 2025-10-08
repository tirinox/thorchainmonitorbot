from lib.cooldown import Cooldown
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.tcy import TcyFullInfo


class TcySummaryNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.tcy.summary.notification
        self.cooldown_sec = cfg.as_interval('cooldown', '3d')
        self.cd = Cooldown(self.deps.db, "TcySummaryNotification", self.cooldown_sec)
        self.last_event = None

    async def on_data(self, sender, e: TcyFullInfo):
        if not e:
            self.logger.error('Empty event!')
            return

        self.last_event = e
        if await self.cd.can_do():
            await self.pass_data_to_listeners(e)
            await self.cd.do()

    async def reset(self):
        await self.cd.clear()
