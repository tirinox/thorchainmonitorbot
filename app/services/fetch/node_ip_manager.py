import logging
import random
from typing import List


class ThorNodeAddressManager:
    @staticmethod
    def connection_url(ip_address, path=''):
        return f'http://{ip_address}:1317{path}'

    def __init__(self, seed, session=None, reload_each_n_request=100):
        assert seed
        self.logger = logging.getLogger('ThorNodeAddressManager')
        self.nodes_ip = []
        self.seed_url = seed
        self._cnt = 0
        self._black_list = set()
        self.reload_each_n_request = reload_each_n_request
        self.session = session
        self._rng = random.SystemRandom()

    async def get_seed_nodes(self):
        assert self.session
        self.logger.info(f'Using seed URL: {self.seed_url}')
        async with self.session.get(self.seed_url) as resp:
            return await resp.json()

    @staticmethod
    def is_ok_node(node_j):
        return (
                node_j['status'] == 'active' and
                not node_j['requested_to_leave'] and
                not node_j['forced_to_leave']
        )

    async def get_thornode_active_list(self, node_ip):
        assert self.session
        url = self.connection_url(node_ip) + "/thorchain/nodeaccounts"
        self.logger.info(f'requesting url: {url}')
        async with self.session.get(url) as resp:
            json = await resp.json()
            nodes = [node['ip_address'] for node in json if self.is_ok_node(node)]
            self.logger.info(f'total nodes loaded: {len(json)}; active: {len(nodes)} ')
            return nodes

    async def reload_nodes_ip(self):
        seed_nodes_ip = await self.get_seed_nodes()
        self._rng.shuffle(seed_nodes_ip)
        for node_ip in seed_nodes_ip:
            try:
                active_list = await self.get_thornode_active_list(node_ip)
                if not active_list:
                    raise ValueError('empty')
                else:
                    self.nodes_ip = active_list
                    break
            except Exception as e:
                self.logger.error(f'failed to get active list from {node_ip}: {e}; next!')

        assert self.nodes_ip

        self.logger.info(f'active nodes loaded: ({len(self.nodes_ip)}) {self.nodes_ip})')
        assert len(self.nodes_ip) > 1

    @property
    def valid_nodes(self):
        return set(self.nodes_ip) - self._black_list

    async def select_node(self):
        return (await self.select_nodes(n=1))[0]

    async def select_nodes(self, n) -> List[str]:
        nodes = self.valid_nodes

        if not nodes or not self.nodes_ip or self._cnt >= self.reload_each_n_request:
            self._cnt = 0
            await self.reload_nodes_ip()
            nodes = self.valid_nodes
        else:
            self._cnt += 1

        ips = self._rng.sample(list(nodes), n)
        return ips

    async def select_node_url(self):
        return self.connection_url(await self.select_node())

    async def blacklist_node(self, ip, reason='?'):
        self.logger.warning(f'blacklisting {ip} reason: {reason}.')
        self._black_list.add(ip)
