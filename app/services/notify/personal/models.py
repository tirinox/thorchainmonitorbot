from typing import List

from services.models.node_info import NodeChange


class BaseChangeTracker:
    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return ch_list
