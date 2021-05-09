import json
import random
from dataclasses import asdict
from typing import List

from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.node_info import NodeInfo, NodeInfoChanges


class NodeInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.node_info.fetch_period)
        super().__init__(deps, sleep_period)
        self.url_gen = get_url_gen_by_network_id(deps.cfg.network_id)

    DB_KEY_OLD_NODE_LIST = 'PreviousNodeInfo'

    async def _get_old_node_info(self) -> List[NodeInfo]:
        try:
            db = self.deps.db
            j = await db.redis.get(self.DB_KEY_OLD_NODE_LIST)
            raw_data_list = json.loads(j)
            return [NodeInfo(**d) for d in raw_data_list]
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            self.logger.exception('get_old_cap error')
            return []

    async def _save_node_infos(self, infos: List[NodeInfo]):
        r = await self.deps.db.get_redis()
        data = [asdict(item) for item in infos]
        await r.set(self.DB_KEY_OLD_NODE_LIST, json.dumps(data))

    async def _extract_changes(self, new_nodes: List[NodeInfo]) -> NodeInfoChanges:
        old_nodes = await self._get_old_node_info()
        if not old_nodes:
            return NodeInfoChanges.empty()

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

        return NodeInfoChanges(nodes_added, nodes_removed, nodes_activated, nodes_deactivated, new_nodes)

    async def fetch_current_node_list(self) -> List[NodeInfo]:
        session = self.deps.session

        url = self.url_gen.url_thor_nodes()
        self.logger.info(f"get Thor nodes: {url}")

        new_nodes = []
        async with session.get(url) as resp:
            raw_nodes = await resp.json()
            for j in raw_nodes:
                new_nodes.append(NodeInfo(
                    status=j['status'],
                    node_address=j['node_address'],
                    bond=int(j['bond']) * THOR_DIVIDER_INV,
                    ip_address=j['ip_address'],
                    version=j['version'],
                    slash_points=int(j['slash_points']),
                    current_award=int(j['current_award']) * THOR_DIVIDER_INV,
                ))

        new_nodes.sort(key=lambda k: (k.status, -k.bond))
        return new_nodes

    async def fetch(self) -> NodeInfoChanges:
        new_nodes = await self.fetch_current_node_list()
        # new_nodes = self._test_churn(new_nodes)  #  debug!!

        results = await self._extract_changes(new_nodes)

        await self._save_node_infos(new_nodes)
        return results

    @staticmethod
    def _test_churn(new_nodes: List[NodeInfo]):
        """
        This is for debug purposes
        """
        new_nodes = list(new_nodes)

        def random_node(nodes):
            return nodes[random.randint(0, len(nodes))]

        if random.uniform(0, 1) > 0.7:
            new_nodes.remove(random_node(new_nodes))

        if random.uniform(0, 1) > 0.3:
            new_nodes.remove(random_node(new_nodes))

        if random.uniform(0, 1) > 0.65:
            node = random_node(new_nodes)
            node.status = node.STANDBY if node.is_active else node.ACTIVE

        if random.uniform(0, 1) > 0.4:
            node = random_node(new_nodes)
            node.status = node.STANDBY if node.is_active else node.ACTIVE

        if random.uniform(0, 1) > 0.2:
            node = random_node(new_nodes)
            node.status = node.STANDBY if node.is_active else node.ACTIVE

        return new_nodes