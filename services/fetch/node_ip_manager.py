import logging
import random

import aiohttp


class ThorNodeAddressManager:
    FALLBACK_THORCHAIN_IP = '3.131.115.233'
    THORCHAIN_SEED_URL = 'https://chaosnet-seed.thorchain.info/'  # all addresses

    @staticmethod
    def connection_url(ip_address):
        ip_address = ip_address if ip_address else ThorNodeAddressManager.FALLBACK_THORCHAIN_IP
        return f'http://{ip_address}:1317'

    def __init__(self, session=None, reload_each_n_request=50):
        self.logger = logging.getLogger('ThorNodeAddressManager')
        self.nodes_ip = []
        self._cnt = 0
        self._black_list = set()
        self.reload_each_n_request = reload_each_n_request
        self.session = session or aiohttp.ClientSession()

    async def get_thorchain_nodes(self):
        async with self.session.get(self.THORCHAIN_SEED_URL) as resp:
            return await resp.json()

    async def reload_nodes_ip(self):
        self.nodes_ip = await self.get_thorchain_nodes()
        self.logger.info(f'nodes loaded: {self.nodes_ip}')
        assert len(self.nodes_ip) > 1

    async def select_node(self):
        nodes = set(self.nodes_ip) - self._black_list

        if not nodes or not self.nodes_ip or self._cnt >= self.reload_each_n_request:
            self._cnt = 0
            await self.reload_nodes_ip()
        else:
            self._cnt += 1

        ip = random.choice(list(nodes)) if nodes else self.FALLBACK_THORCHAIN_IP
        return ip

    async def select_node_url(self):
        return self.connection_url(await self.select_node())

    async def blacklist_node(self, ip):
        self._black_list.add(ip)
