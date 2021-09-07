from typing import List

from services.lib.depcont import DepContainer
from services.notify.personal.models import BaseChangeTracker
from services.models.node_info import NodeChange


class ChainHeightTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_node_changes(self, node_address) -> List[NodeChange]:
        if not node_address:
            return []
        return []
