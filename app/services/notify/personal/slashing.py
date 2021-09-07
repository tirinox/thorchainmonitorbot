from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeChangeType, NodeChange
from services.notify.personal.models import BaseChangeTracker


class SlashPointTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, pc_node_map: MapAddressToPrevAndCurrNode) -> List[NodeChange]:
        changes = []
        for a, (prev, curr) in pc_node_map.items():
            if prev.slash_points != curr.slash_points:
                changes.append(
                    NodeChange(
                        prev.node_address, NodeChangeType.SLASHING, (prev.slash_points, curr.slash_points)
                    )
                )
        return changes
