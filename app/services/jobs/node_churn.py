from typing import List

from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_db import NodeStateDatabase
from services.models.node_info import NodeSetChanges, NodeInfo


class NodeChurnDetector(WithDelegates, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.logger = class_logger(self)
        self.deps = deps
        self._node_db = NodeStateDatabase(self.deps)

    async def get_last_node_info(self) -> List[NodeInfo]:
        return await self._node_db.get_last_node_info_list()

    async def compare_with_new_nodes(self, new_nodes: List[NodeInfo]) -> NodeSetChanges:
        old_nodes = await self.get_last_node_info()
        changes = self.extract_changes(new_nodes, old_nodes)
        return changes

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
        result = await self.compare_with_new_nodes(info_list)

        await self._node_db.save_node_info_list(info_list)
        self.logger.info(f'Saved previous state of {len(info_list)} nodes.')

        try:
            # Fill out some additional data
            result.block_no = self.deps.last_block_store.last_thor_block
            result.vault_migrating = sender.thor_network.vaults_migrating
        except AttributeError:
            self.logger.error(f'Cannot get vault_migrating from {sender}')

        # result = self._dbg_modification(result)

        await self.pass_data_to_listeners(result, (sender, self))

    # ------------------------------------------------------------------------------------------------------------------

    def _dbg_modification(self, data: NodeSetChanges) -> NodeSetChanges:
        # 1. new version
        # for i in range(1, 55):
        #     data.nodes_all[i].version = '1.90.1'
        # data.nodes_all[1].version = '0.88.5'

        # 2. Min versions
        # for n in data.nodes_all:
        #     if random.uniform(0, 1) > 0.5:
        #         n.version = '0.57.5'
        #     n.version = '0.61.66'
        # data.nodes_all[0].version = '0.61.63'

        # 3. Upgrade
        # progress = 0.99  # 0..1
        # for n in data.nodes_all:
        #     if random.uniform(0, 1) <= progress:
        #         n.version = '0.60.6'

        # data.nodes_added.append(data.nodes_all[0])

        # simulate churn
        data.nodes_activated.append(data.nodes_all[1])
        data.nodes_activated.append(data.nodes_all[2])
        data.nodes_activated.append(data.nodes_all[3])
        data.nodes_deactivated.append(data.nodes_all[4])
        data.nodes_deactivated.append(data.nodes_all[5])
        data.nodes_deactivated.append(data.nodes_all[6])
        data.nodes_deactivated.append(data.nodes_all[7])
        data.nodes_deactivated.append(data.nodes_all[8])
        data.nodes_removed.append(data.nodes_all[9])

        return data

    # fixme: remove
    # standby_nodes = [n for n in info_list if n.is_standby and n.bond > 10000]
    # if standby_nodes:
    #     info_list.remove(standby_nodes[2])
    # fixme: remove
