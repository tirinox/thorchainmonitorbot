import asyncio
from typing import List

from aiothornode.nodeclient import ThorNodeClient

from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id, MidgardURLGenV2
from services.lib.utils import class_logger
from services.models.time_series import TimeSeries

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

    def __init__(self, d: DepContainer):
        network_id = d.cfg.network_id
        self.deps = d
        self.n_tries = int(d.cfg.get_pure('thor.midgard.tries', 3))
        self.url_gen = get_url_gen_by_network_id(network_id)
        self.parser = get_parser_by_network_id(network_id)
        self.logger = class_logger(self)
        self.stats_series = TimeSeries('MidgardStats', self.deps.db)

    async def _request_json_from_midgard_by_ip(self, ip_address: str, path: str):
        port = DEFAULT_MIDGARD_PORT
        path = path.lstrip('/')
        full_url = f'http://{ip_address}:{port}/v2/{path}'

        self.logger.info(f"Getting Midgard endpoint: {full_url}")
        try:
            async with self.deps.session.get(full_url) as resp:
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
        clients: List[ThorNodeClient] = await self.deps.thor_connector.get_random_clients(self.n_tries)
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
