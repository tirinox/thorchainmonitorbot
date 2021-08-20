import json
from dataclasses import asdict
from typing import List

from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges, NodeInfo


class NodeChurnDetector:
    def __init__(self, deps: DepContainer):
        self.logger = class_logger(self)
        self.deps = deps

    DB_KEY_OLD_NODE_LIST = 'PreviousNodeInfo'

    async def get_last_node_info(self) -> List[NodeInfo]:
        try:
            db = self.deps.db
            j = await db.redis.get(self.DB_KEY_OLD_NODE_LIST)
            raw_data_list = json.loads(j)
            return [NodeInfo(**d) for d in raw_data_list]
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            self.logger.exception('get_last_node_info db error')
            return []

    async def _save_node_infos(self, infos: List[NodeInfo]):
        r = await self.deps.db.get_redis()
        data = [asdict(item) for item in infos]
        await r.set(self.DB_KEY_OLD_NODE_LIST, json.dumps(data))

    async def extract_changes(self, new_nodes: List[NodeInfo]) -> NodeSetChanges:
        old_nodes = await self.get_last_node_info()
        if not old_nodes:
            return NodeSetChanges.empty()

        new_node_ids = set(n.ident for n in new_nodes)
        old_node_ids = set(n.ident for n in old_nodes)
        old_node_active_ids = set(n.ident for n in old_nodes if n.is_active)

        nodes_activated = []
        nodes_deactivated = []
        nodes_added = []
        nodes_removed = []

        for n in new_nodes:
            if n.is_active and n.ident not in old_node_active_ids:
                nodes_activated.append(n)
            elif not n.is_active and n.ident in old_node_active_ids:
                nodes_deactivated.append(n)

            if n.ident not in old_node_ids:
                nodes_added.append(n)

        for old_n in old_nodes:
            if old_n.ident not in new_node_ids:
                nodes_removed.append(old_n)

        return NodeSetChanges(nodes_added,
                              nodes_removed,
                              nodes_activated,
                              nodes_deactivated,
                              nodes_all=new_nodes,
                              nodes_previous=old_nodes)
