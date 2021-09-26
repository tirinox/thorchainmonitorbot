from typing import NamedTuple, Dict, List, Union

import ujson

from services.lib.db import DB
from services.lib.utils import nested_set, nested_get

JSONObject = Dict[str, Union['JSONObject', List, str, int, float]]


class UserDataCache(NamedTuple):
    """
    node -> service -> data
    user -> node -> service -> data
    """
    node_service_data: JSONObject
    user_node_service_data: JSONObject

    DB_KEY = 'NodeOp:UserCache'

    @classmethod
    def from_json(cls, j):
        if not j:
            return cls({}, {})
        j = ujson.loads(j) if isinstance(j, str) else j
        return cls(
            node_service_data=j.get('node_service_data', {}),
            user_node_service_data=j.get('user_node_service_data', {})
        )

    async def save(self, db: DB):
        json_str = ujson.dumps(self._asdict())
        await db.redis.set(self.DB_KEY, json_str)

    def __str__(self) -> str:
        return f"UserDataCache(nodes={len(self.node_service_data)}, users={len(self.user_node_service_data)})"

    def get_node_data(self, node, service):
        return nested_get(self.node_service_data, (node, service))

    def get_user_data(self, user, node, service):
        return nested_get(self.user_node_service_data, (user, node, service))

    def set_node_data(self, node, service, data):
        nested_set(self.node_service_data, (node, service), data)

    def set_user_data(self, user, node, service, data):
        nested_set(self.user_node_service_data, (user, node, service), data)

    @classmethod
    async def load(cls, db: DB):
        json_str = await db.redis.get(cls.DB_KEY)
        return cls.from_json(json_str)
