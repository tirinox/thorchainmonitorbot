from typing import List

from services.lib.db_many2many import ManyToManySet
from services.lib.depcont import DepContainer


class NodeWatcherStorage:
    def __init__(self, d: DepContainer, user_id: str):
        self.deps = d
        self.user_id = user_id
        self.many2many = ManyToManySet(d.db, 'UserID', 'NodeIP')

    async def add_user_to_node(self, node: str):
        if node and self.user_id:
            await self.many2many.associate(self.user_id, node)

    async def add_user_to_node_list(self, nodes: List[str]):
        if nodes and all(nodes) and self.user_id:
            await self.many2many.associate_many([self.user_id], nodes)

    async def remove_user_nodes(self, nodes: List[str]):
        for node in nodes:
            if node:
                await self.many2many.remove_one_item(self.user_id, node)

    async def clear_user_nodes(self):
        await self.many2many.remove_all_rights(self.user_id)

    async def all_users_for_node(self, node: str) -> List[str]:
        return await self.many2many.all_lefts_for_right_one(node)

    async def all_nodes_for_user(self) -> List[str]:
        return await self.many2many.all_rights_for_left_one(self.user_id)
