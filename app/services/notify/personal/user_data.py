from typing import NamedTuple, Dict, List, Union

import ujson

from services.lib.db import DB
from services.lib.utils import make_nested_default_dict

JSONObject = Dict[str, Union['JSONObject', List, str, int, float]]


class UserDataCache(NamedTuple):
    """
    node -> service -> data
    user -> node -> service -> data
    """
    node_service_data: Dict
    user_node_service_data: Dict

    DB_KEY = 'NodeOp:UserCache'

    @classmethod
    def from_json(cls, j):
        if not j:
            node_service_data = {}
            user_node_service_data = {}
        else:
            j = ujson.loads(j) if isinstance(j, str) else j
            node_service_data = j.get('node_service_data', {})
            user_node_service_data = j.get('user_node_service_data', {})
        return cls(
            make_nested_default_dict(node_service_data),
            make_nested_default_dict(user_node_service_data)
        )

    async def save(self, db: DB):
        json_str = ujson.dumps(self._asdict())
        await db.redis.set(self.DB_KEY, json_str)

    def __str__(self) -> str:
        return f"UserDataCache(nodes={len(self.node_service_data)}, users={len(self.user_node_service_data)})"

    @classmethod
    async def load(cls, db: DB):
        json_str = await db.redis.get(cls.DB_KEY)
        return cls.from_json(json_str)
