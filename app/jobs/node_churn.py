from typing import List

from jobs.fetch.node_info import NodeInfoFetcher
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.node_db import NodeStateDatabase
from models.node_info import NodeSetChanges, NodeInfo


class NodeChurnDetector(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._node_db = NodeStateDatabase(self.deps)

    async def get_last_node_info(self) -> List[NodeInfo]:
        return await self._node_db.get_last_node_info_list()

    @staticmethod
    def extract_changes(new_nodes: List[NodeInfo], old_nodes: List[NodeInfo]) -> NodeSetChanges:
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

        return NodeSetChanges(
            nodes_added,
            nodes_removed,
            nodes_activated,
            nodes_deactivated,
            nodes_all=new_nodes,
            nodes_previous=old_nodes
        )

    async def on_data(self, sender: NodeInfoFetcher, info_list: List[NodeInfo]):
        old_nodes = await self.get_last_node_info()
        changes: NodeSetChanges = self.extract_changes(info_list, old_nodes)

        await self._node_db.save_node_info_list(info_list)
        self.logger.info(f'Saved state of THORNode set: {len(info_list)} nodes.')

        try:
            # Fill out some additional data
            network_info = await self.deps.thor_connector.query_network()
            changes.vaults_migrating = network_info.vaults_migrating
        except AttributeError:
            self.logger.error(f'Cannot get vaults_migrating from {sender}')

        changes.block_no = await self.deps.last_block_cache.get_thor_block()

        await self.pass_data_to_listeners(changes, (sender, self))
