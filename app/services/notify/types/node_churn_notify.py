import logging

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import MINUTE
from services.lib.depcont import DepContainer
from services.models.node_info import NodeInfoChanges


class NodeChurnNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cd = Cooldown(self.deps.db, 'NodeChurnNotification', MINUTE * 10, 5)

    async def on_data(self, sender, data: NodeInfoChanges):
        if not data.is_empty:
            if await self.cd.can_do():
                await self._notify_when_cap_changed(data)
                await self.cd.do()

    async def _notify_when_cap_changed(self, changes: NodeInfoChanges):
        await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                  BaseLocalization.notification_text_for_node_churn,
                                                                  changes)
