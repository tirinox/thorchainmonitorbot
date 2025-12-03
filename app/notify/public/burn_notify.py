from jobs.rune_burn_recorder import RuneBurnRecorder
from lib.cooldown import Cooldown
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.mimir import MimirTuple


class BurnNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        notify_cd_sec = deps.cfg.as_interval('supply.rune_burn.notification.cooldown', '2d')
        self.cd = Cooldown(self.deps.db, 'RuneBurn', notify_cd_sec)
        self.recorder = RuneBurnRecorder(self.deps)

    async def on_data(self, sender, _: MimirTuple):
        if event := await self.recorder.get_event():
            if await self.cd.can_do():
                await self.pass_data_to_listeners(event)
                await self.cd.do()
