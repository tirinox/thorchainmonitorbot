import asyncio
import json
from hashlib import sha256

from services.fetch.node_ip_manager import ThorNodeAddressManager


class ThorNode:
    def __init__(self, node_ip_man: ThorNodeAddressManager, session, cohort_size=5, consensus=3):
        self.node_ip_man = node_ip_man
        self.session = session
        self.cohort_size = cohort_size
        self.consensus = consensus

    async def _request_one_node(self, node_ip, path):
        url = self.node_ip_man.connection_url(node_ip, path)
        async with self.session.get(url) as resp:
            return await resp.json()

    async def request(self, path: str):
        if not path.startswith('/'):
            path = '/' + path
        node_ips = await self.node_ip_man.select_nodes(self.cohort_size)
        responses = await asyncio.gather(*[self._request_one_node(ip, path) for ip in node_ips])
        hashes = [sha256(json.encode(r)).hexdigest() for r in responses]

