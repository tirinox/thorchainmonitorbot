from typing import List

from services.models.node_info import NodeChange


class BaseChangeTracker:
    async def get_node_changes(self, node_address, *args, **kwargs) -> List[NodeChange]:
        return []

    async def get_all_changes(self, *args, **kwargs) -> List[NodeChange]:
        return []

    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return ch_list

