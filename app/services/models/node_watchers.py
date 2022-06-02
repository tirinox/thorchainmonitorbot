from typing import List, Dict

from services.lib.db import DB
from services.lib.db_many2many import ManyToManySet


class UserWatchlist:
    def __init__(self, db: DB, watch_category_name):
        self.db = db
        self.many2many = ManyToManySet(db, 'UserID', watch_category_name)

    async def add_user_to_node(self, user_id, node: str):
        if node and user_id:
            await self.many2many.associate(user_id, node)

    async def set_user_to_node(self, user_id, node: str, value: bool):
        if value:
            await self.add_user_to_node(user_id, node)
        else:
            await self.remove_user_node(user_id, node)

    async def add_user_to_node_list(self, user_id, nodes: List[str]):
        if nodes and all(nodes) and user_id:
            await self.many2many.associate_many([user_id], nodes)

    async def remove_user_node(self, user_id, node: str):
        if user_id and node:
            await self.many2many.remove_one_item(user_id, node)

    async def remove_user_nodes(self, user_id, nodes: List[str]):
        for node in nodes:
            await self.remove_user_node(user_id, node)

    async def clear_user_nodes(self, user_id):
        await self.many2many.remove_all_rights(user_id)

    async def all_users_for_node(self, node: str) -> List[str]:
        return await self.many2many.all_lefts_for_right_one(node)

    async def all_users_for_many_nodes(self, nodes: iter) -> Dict[str, List[str]]:
        return await self.many2many.all_lefts_for_many_rights(nodes, flatten=False)

    async def all_nodes_for_user(self, user_id) -> List[str]:
        return await self.many2many.all_rights_for_left_one(user_id)

    async def all_users(self):
        return await self.many2many.all_lefts()

    async def has_node(self, node, user_id):
        rights = await self.all_nodes_for_user(user_id)
        return node in rights


class NamedNodeStorage:
    def __init__(self, db: DB):
        self.db = db

    @staticmethod
    def key_for_node_names(user_id, node):
        return f'User:{user_id}:SetName:{node}'

    async def set_node_name(self, user_id: str, node: str, name: str):
        if node:
            r = await self.db.get_redis()
            k = self.key_for_node_names(user_id, node)
            if name:
                await r.set(k, name)
            else:
                await r.delete(k)

    async def get_node_names(self, node_list: list):
        if not node_list:
            return {}
        r = await self.db.get_redis()
        names = await r.mget(*map(self.key_for_node_names, node_list))
        return dict(zip(node_list, names))


class NodeWatcherStorage(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, watch_category_name='WatchNodeIP')
        self.node_name_storage = NamedNodeStorage(db)


class AlertWatchers(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, watch_category_name='WatchAlerts')
