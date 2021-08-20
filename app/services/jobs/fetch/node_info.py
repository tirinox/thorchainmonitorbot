import random
from typing import List

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.geo_ip import GeoIPManager
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.node_info import NodeInfo, NetworkNodeIpInfo


class NodeInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.node_info.fetch_period)
        super().__init__(deps, sleep_period)
        self.url_gen = get_url_gen_by_network_id(deps.cfg.network_id)

    async def fetch_current_node_list(self) -> List[NodeInfo]:
        session = self.deps.session

        url = self.url_gen.url_thor_nodes()
        self.logger.info(f"get Thor nodes: {url}")

        new_nodes = []
        async with session.get(url) as resp:
            raw_nodes = await resp.json()
            for j in raw_nodes:
                new_nodes.append(NodeInfo.from_json(j))

        new_nodes.sort(key=lambda k: (k.status, -k.bond))
        return new_nodes

    async def fetch(self) -> List[NodeInfo]:
        return await self.fetch_current_node_list()

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

    async def get_node_list_and_geo_info(self, node_list=None):
        if node_list is None:
            node_list = await self.fetch_current_node_list()

        ip_addresses = [node.ip_address for node in node_list if node.ip_address]

        geo_ip = GeoIPManager(self.deps)
        ip_info_list = await geo_ip.get_ip_info_bulk(ip_addresses)
        ip_info_dict = {n["ip"]: n for n in ip_info_list if n and 'ip' in n}

        return NetworkNodeIpInfo(
            node_list,
            ip_info_dict
        )
