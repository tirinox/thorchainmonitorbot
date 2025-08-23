from time import perf_counter
from typing import List

from jobs.fetch.cached.base import CachedDataSource
from jobs.fetch.circulating import RuneCirculatingSupplyFetcher
from lib.constants import THOR_BLOCK_TIME
from lib.depcont import DepContainer
from lib.geo_ip import GeoIPManager
from models.node_info import NodeInfo, NetworkNodes


class NodeCache(CachedDataSource[NetworkNodes]):
    ATTEMPTS = 5

    def __init__(self, deps: DepContainer):
        super().__init__(cache_period=THOR_BLOCK_TIME, retry_times=self.ATTEMPTS)
        self.deps = deps
        self._geo_ip = GeoIPManager(self.deps)

    async def _load(self) -> NetworkNodes:
        nodes = await self.fetch_current_node_list()
        return await self.load_geo_info_for_nodes(nodes)

    async def load_geo_info_for_nodes(self, nodes: List[NodeInfo]) -> NetworkNodes:
        ip_info_dict = {}
        if nodes:
            try:
                ip_info_dict = await self._load_geo_info(nodes)
            except Exception as e:
                self.logger.exception(f'load_geo_info failed ({e}), but it is not that bad, I will go on.',
                                      stack_info=True)

        supply_fetcher = RuneCirculatingSupplyFetcher(self.deps.session, self.deps.thor_connector,
                                                     self.deps.midgard_connector)

        total_rune_supply = await supply_fetcher.get_thor_rune_total_supply()

        return NetworkNodes(
            nodes,
            ip_info_dict,
            total_rune_supply=total_rune_supply
        )

    async def fetch_current_node_list(self) -> List[NodeInfo]:
        thor = self.deps.thor_connector
        raw_nodes = await thor.query_raw(thor.env.path_nodes)

        nodes = []
        for j in raw_nodes:
            node = NodeInfo.from_json(j)
            nodes.append(node)

        nodes.sort(key=lambda k: (k.status, -k.bond))

        return nodes

    async def _load_geo_info(self, node_list):
        ip_addresses = [node.ip_address for node in node_list if node.ip_address]

        t0 = perf_counter()

        unique_ip_addresses = list(set(ip_addresses))
        self.logger.info(
            f'Requesting geo info for {len(ip_addresses)} IP addresses. Unique: {len(unique_ip_addresses)}')

        ip_info_dict = await self._geo_ip.get_ip_info_bulk_as_dict(ip_addresses)

        time_elapsed = perf_counter() - t0
        self.logger.info(f'Got {len(ip_info_dict)} IP address info pieces. It took: {time_elapsed:.3f} sec.')

        if not ip_info_dict:
            self.logger.warning(f'Failed to get IP info ({len(ip_addresses)} addresses were requested)')

        for node in node_list:
            node.ip_info = ip_info_dict.get(node.ip_address)

        return ip_info_dict
