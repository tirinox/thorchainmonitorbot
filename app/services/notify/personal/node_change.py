import asyncio

from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges


class NodeChangePersonalNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

    async def on_data(self, sender, changes: NodeSetChanges):
        asyncio.create_task(self._bg_job(changes))  # long-running job goes to the background!

    async def _bg_job(self, changes: NodeSetChanges):
        # 1. compare old and new?
        # 2. extract changes
        # 3. get list of changed nodes
        # 4. get list of user who watch those nodes
        # 5. for user in Watchers:
        #    for node in user.nodes:
        #     changes = changes[node.address]
        #     for change in changes:
        #        user.sendMessage(format(change))
        ...

# Changes?
#  1. version update
#  2. new version detected, consider upgrade?
#  3. slash point increase (over threshold)
#  4. bond changes (over threshold)
#  5. ip address change?
#  6. went offline?
#  7. went online!
#  8. block height is not increasing
#  9. block height is not increasing on CHAIN?!
#  10. your node churned in / out
#  11. your node became a candidate for churn in (dropped?)
