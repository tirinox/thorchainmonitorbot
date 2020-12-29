import asyncio
import logging
from collections import Counter
from hashlib import sha256

import ujson
from aiohttp import ClientSession, ClientConnectorError

from services.fetch.node_ip_manager import ThorNodeAddressManager


class ThorNode:
    def __init__(self, node_ip_man: ThorNodeAddressManager, session: ClientSession, cohort_size=5, consensus=3):
        self.node_ip_man = node_ip_man
        self.session = session

        self.cohort_size = cohort_size
        self.consensus = consensus
        assert consensus > 0
        assert cohort_size >= consensus

        self.timeout = 3.0
        self.logger = logging.getLogger('ThorNode')

    async def _request_one_node_as_text(self, node_ip, path):
        url = self.node_ip_man.connection_url(node_ip, path)
        try:
            async with self.session.get(url, timeout=self.timeout) as resp:
                return await resp.text()
        except (ClientConnectorError, asyncio.TimeoutError) as e:
            self.logger.warning(f'Cannot connect to THORNode ({node_ip}) for "{path}" (err: {e}).')
            return ''

    def _consensus_response(self, text_responses):
        hash_dict = {i: sha256(r.encode('utf-8')).hexdigest() for i, r in enumerate(text_responses)}
        counter = Counter(hash_dict.values())
        most_hash, most_freq = counter.most_common(1)[0]
        if most_freq >= self.consensus > 0:
            best_index = next(i for i, this_hash in hash_dict.items() if this_hash == most_hash)
            return text_responses[best_index], most_freq / self.cohort_size
        else:
            return None, 0.0

    async def request_random_node(self, path: str):
        node_id = await self.node_ip_man.select_node()
        text = await self._request_one_node_as_text(node_id, path)
        return ujson.loads(text)

    async def request(self, path: str):
        if not path.startswith('/'):
            path = '/' + path
        node_ips = await self.node_ip_man.select_nodes(self.cohort_size)
        # node_ips[0] = '127.0.0.1'  # debug

        self.logger.info(f'Start request to Thor node "{path}"')
        text_responses = await asyncio.gather(*[self._request_one_node_as_text(ip, path) for ip in node_ips])
        best_text_response, ratio = self._consensus_response(text_responses)
        if best_text_response is None:
            self.logger.error(f'No consensus reached between nodes: {node_ips} for request "{path}"!')
            return None
        else:
            self.logger.info(f'Success for the request "{path}" consensus: {(ratio * 100.0):.0f}%')
            return ujson.loads(best_text_response)
