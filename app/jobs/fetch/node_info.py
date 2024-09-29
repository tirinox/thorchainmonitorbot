from time import perf_counter
from typing import List, Optional

from api.aionode.types import ThorNetwork

from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from lib.geo_ip import GeoIPManager
from models.node_info import NodeInfo, NetworkNodeIpInfo


class NodeInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.node_info.fetch_period)
        super().__init__(deps, sleep_period)

        self._geo_ip = GeoIPManager(self.deps)
        self.thor_network: Optional[ThorNetwork] = None

    async def fetch_current_node_list(self) -> List[NodeInfo]:
        thor = self.deps.thor_connector
        raw_nodes = await thor.query_raw(thor.env.path_nodes)

        nodes = []
        for j in raw_nodes:
            node = NodeInfo.from_json(j)
            nodes.append(node)

        nodes.sort(key=lambda k: (k.status, -k.bond))

        return nodes

    async def fetch(self) -> List[NodeInfo]:
        nodes = await self.fetch_current_node_list()

        if nodes:
            try:
                await self.get_node_list_and_geo_info(nodes)
            except Exception as e:
                self.logger.exception(
                    f'get_node_list_and_geo_info failed ({e}), but it is not that bad, I will go on.', stack_info=True)

            self.deps.node_holder.nodes = nodes

        self.thor_network = await self.deps.thor_connector.query_network()
        if self.thor_network:
            self.logger.info(f"ThorNetwork = {self.thor_network}")

        return nodes

    async def get_node_list_and_geo_info(self, node_list=None) -> NetworkNodeIpInfo:
        if node_list is None:
            node_list = await self.fetch_current_node_list()

        ip_addresses = [node.ip_address for node in node_list if node.ip_address]

        t0 = perf_counter()

        unique_ip_addresses = list(set(ip_addresses))
        self.logger.info(f'Requesting geo info for {len(ip_addresses)} IP addresses. Unique: {len(unique_ip_addresses)}')

        ip_info_dict = await self._geo_ip.get_ip_info_bulk_as_dict(ip_addresses)

        time_elapsed = perf_counter() - t0
        self.logger.info(f'Got {len(ip_info_dict)} IP address info pieces. It took: {time_elapsed:.3f} sec.')

        if not ip_info_dict:
            self.logger.warning(f'Failed to get IP info ({len(ip_addresses)} addresses were requested)')

        for node in node_list:
            node.ip_info = ip_info_dict.get(node.ip_address, {})

        return NetworkNodeIpInfo(
            node_list,
            ip_info_dict
        )
