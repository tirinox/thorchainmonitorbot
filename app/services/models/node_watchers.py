from dataclasses import field, dataclass
from typing import List, Dict

from services.lib.db_many2many import ManyToManySet
from services.lib.depcont import DepContainer
from services.models.node_info import NodeInfo


@dataclass
class NodeWatchInfo:
    node_address: str = ''
    last_info: NodeInfo = field(default_factory=NodeInfo)
    last_online_ts: int = 0


class NodeWatcherStorage:
    def __init__(self, d: DepContainer, user_id: str = ''):
        self.deps = d
        self.user_id = user_id
        self.many2many = ManyToManySet(d.db, 'UserID', 'WatchNodeIP')

    def key_for_node_names(self, node):
        return f'User.{self.user_id}.SetName.{node}'

    async def set_node_name(self, node: str, name: str):
        if node:
            r = await self.deps.db.get_redis()
            k = self.key_for_node_names(node)
            if name:
                await r.set(k, name)
            else:
                await r.delete(k)

    async def get_node_names(self, node_list: list):
        if not node_list:
            return {}
        r = await self.deps.db.get_redis()
        names = await r.mget(*map(self.key_for_node_names, node_list), encoding='utf-8')
        return dict(zip(node_list, names))

    async def add_user_to_node(self, node: str, name: str):
        if node and self.user_id:
            await self.many2many.associate(self.user_id, node)
            if name:
                await self.set_node_name(node, name)

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

    async def all_users_for_many_nodes(self, nodes: iter) -> Dict[str, List[str]]:
        return await self.many2many.all_lefts_for_many_rights(nodes, flatten=False)

    async def all_nodes_for_user(self) -> List[str]:
        return await self.many2many.all_rights_for_left_one(self.user_id)

    async def all_nodes_with_names_for_user(self) -> Dict[str, str]:
        nodes = await self.all_nodes_for_user()
        return await self.get_node_names(nodes)

    async def get_user_settings(self, user_id):
        context = self.deps.dp.current_state(chat=user_id, user=user_id)
        return await context.get_data()
