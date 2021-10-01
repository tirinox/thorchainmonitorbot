import asyncio
from typing import List

import aiohttp
from aiothornode.connector import ThorConnector
from aiothornode.nodeclient import ThorNodeClient

from services.lib.utils import class_logger

DEFAULT_MIDGARD_PORT = 8080


class MidgardConnector:
    """
    Tasks:
    1. Proxy Midgard requests
    2. Error protection
    3. Retries
    4. Error statistics
    5. Select other Midgard if many errors on official Midgard
    Todo: one task -> one class
    """

    ERROR_RESPONSE = 'ERROR_Midgard'
    ERROR_NO_CLIENT = 'ERROR_NoClient'

    def __init__(self, session: aiohttp.ClientSession, thor: ThorConnector, retry_number=3):
        self.logger = class_logger(self)
        self.thor = thor
        self.session = session
        self.retries = retry_number

    async def _request_json_from_midgard_by_ip(self, ip_address: str, path: str):
        port = DEFAULT_MIDGARD_PORT
        path = path.lstrip('/')
        full_url = f'http://{ip_address}:{port}/v2/{path}'

        self.logger.info(f"Getting Midgard endpoint: {full_url}")
        try:
            async with self.session.get(full_url) as resp:
                if resp.status != 200:
                    try:
                        answer = resp.content[:200]
                    except TypeError:
                        answer = 'unknown'
                    self.logger.warning(f'Midgard not OK response {resp.status = }, "{answer}"!')
                    return self.ERROR_RESPONSE
                j = await resp.json()
                return j
        except Exception as e:
            self.logger.error(f'Midgard exception: {e!s}.')
            return self.ERROR_RESPONSE

    async def request_random_midgard(self, path: str):
        clients: List[ThorNodeClient] = await self.thor.get_random_clients(self.retries)
        if not clients:
            self.logger.error(f'No THOR clients connected for path "{path}"')
            return None

        tasks = [self._request_json_from_midgard_by_ip(c.node_ip, path) for c in clients]
        results = await asyncio.gather(*tasks)
        for result in results:
            if result != self.ERROR_RESPONSE:
                return result

        self.logger.error(f'No good response for path "{path}"')
        return None
