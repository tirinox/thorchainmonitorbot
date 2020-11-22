import logging
import random


class ThorNodeAddressManager:
    FALLBACK_THORCHAIN_IP = '54.234.193.102'
    THORCHAIN_SEED_URL = 'https://chaosnet-seed.thorchain.info/'  # all addresses

    @staticmethod
    def connection_url(ip_address):
        ip_address = ip_address if ip_address else ThorNodeAddressManager.FALLBACK_THORCHAIN_IP
        return f'http://{ip_address}:1317'

    def __init__(self, session=None, reload_each_n_request=100):
        self.logger = logging.getLogger('ThorNodeAddressManager')
        self.nodes_ip = []
        self._cnt = 0
        self._black_list = set()
        self.reload_each_n_request = reload_each_n_request
        self.session = session

    async def get_seed_nodes(self):
        assert self.session
        async with self.session.get(self.THORCHAIN_SEED_URL) as resp:
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
            self.logger.info(f'total: {len(nodes)}')
            return nodes

    async def reload_nodes_ip(self):
        seed_nodes_ip = await self.get_seed_nodes()
        random.shuffle(seed_nodes_ip)
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

        self.logger.info(f'nodes loaded: {self.nodes_ip}')
        assert len(self.nodes_ip) > 1

    @property
    def valid_nodes(self):
        return set(self.nodes_ip) - self._black_list

    async def select_node(self):
        nodes = self.valid_nodes

        if not nodes or not self.nodes_ip or self._cnt >= self.reload_each_n_request:
            self._cnt = 0
            await self.reload_nodes_ip()
            nodes = self.valid_nodes
        else:
            self._cnt += 1

        ip = random.choice(list(nodes)) if nodes else self.FALLBACK_THORCHAIN_IP
        return ip

    async def select_node_url(self):
        return self.connection_url(await self.select_node())

    async def blacklist_node(self, ip, reason='?'):
        self.logger.warning(f'blacklisting {ip} reason: {reason}.')
        self._black_list.add(ip)

    __instance = None

    @classmethod
    def shared(cls, *args, **kwargs) -> 'ThorNodeAddressManager':
        if not cls.__instance:
            cls.__instance = cls(*args, **kwargs)
        return cls.__instance
