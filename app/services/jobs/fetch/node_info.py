import random
from typing import List

from services.jobs.fetch.base import BaseFetcher
from services.jobs.node_churn import NodeStateDatabase
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.geo_ip import GeoIPManager
from services.lib.midgard.urlgen import free_url_gen
from services.models.node_info import NodeInfo, NetworkNodeIpInfo


class NodeInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.node_info.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch_current_node_list(self) -> List[NodeInfo]:
        raw_nodes = await self.deps.midgard_connector.request_random_midgard(
            free_url_gen.url_thor_nodes()
        )

        if raw_nodes is None:
            self.logger.error('not found!')
            raise FileNotFoundError('node_list')

        new_nodes = []
        for j in raw_nodes:
            new_nodes.append(NodeInfo.from_json(j))
        new_nodes.sort(key=lambda k: (k.status, -k.bond))

        # new_nodes = self._test_churn(new_nodes)  # fixme: debug
        return new_nodes

    async def fetch(self) -> List[NodeInfo]:
        return await self.fetch_current_node_list()

    @staticmethod
    def _test_churn(new_nodes: List[NodeInfo]):
        """
        This is for debug purposes
        """
        new_nodes = list(new_nodes)

        new_nodes[0].version = '0.68.6'  # version fun?

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

    async def post_action(self, info_list: List[NodeInfo]):
        await NodeStateDatabase(self.deps).save_node_info_list(info_list)
        self.logger.info(f'Saved previous state of {len(info_list)} nodes.')

        # fixme: debug(!) ------ 8< -------
        # from collections import defaultdict
        # chain_block_height = defaultdict(int)
        # for node in info_list:
        #     if not node.observe_chains:
        #         continue
        #     for chain_info in node.observe_chains:
        #         chain = chain_info['chain']
        #         height = int(chain_info['height'])
        #         if chain and height:
        #             chain_block_height[chain] = max(chain_block_height[chain], height)
        #     # chain_block_height[Chains.THOR].append(node.active_block_height) # todo!
        # print('my height (!)', chain_block_height)
        # fixme: debug(!) ------ 8< -------


