import json
from dataclasses import asdict
from typing import List

from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import NodeInfo


class NodeStateDatabase:
    DB_KEY_OLD_NODE_LIST = 'NodeChurn:PreviousNodeInfo'

    def __init__(self, deps: DepContainer, key=None):
        self.logger = class_logger(self)
        self.deps = deps
        self.key = key or self.DB_KEY_OLD_NODE_LIST

    async def get_last_node_info_list(self) -> List[NodeInfo]:
        try:
            db = self.deps.db
            j = await db.redis.get(self.key)
            raw_data_list = json.loads(j)
            return [NodeInfo(**d) for d in raw_data_list]
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            self.logger.exception('get_last_node_info db error')
            return []

    async def save_node_info_list(self, info_list: List[NodeInfo]):
        if not info_list:
            return
        r = await self.deps.db.get_redis()
        data = [asdict(item) for item in info_list]
        await r.set(self.key, json.dumps(data))
