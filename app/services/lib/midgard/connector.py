import logging

from aiohttp import ClientSession
from aiothornode.connector import ThorConnector

from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.time_series import TimeSeries

ERROR_RESPONSE = 'ERROR_Midgard'

class MidgardConnector:
    """
    Tasks:
    1. Proxy Midgard requests
    2. Error protection
    3. Retries
    4. Error statistics
    5. Select other Midgard if many errors on official Midgard
    Todo: one task -> one class please sir 🇮🇳
    """
    def __init__(self, d: DepContainer):
        network_id = d.cfg.network_id
        self.deps = d
        self.url_gen = get_url_gen_by_network_id(network_id)
        self.parser = get_parser_by_network_id(network_id)
        self.logger = logging.Logger(self.__class__.__name__)
        self.stats_series = TimeSeries('MidgardStats', self.deps.db)

    async def raw_request(self, url: str, path: str):
        full_url = url.rstrip('/') + '/' + path.lstrip('/')
        self.logger.info(f"Getting Midgard endpoint: {full_url}")
        try:
            async with self.deps.session.get(url) as resp:
                if resp.status != 200:
                    answer = resp.content[:200]
                    self.logger.warning(f'Midgard not OK response {resp.status = }, content "{answer}"!')
                    return ERROR_RESPONSE
                j = await resp.json()
                return j
        except Exception as e:
            self.logger.error(f'Midgard exception: {e!s}.')
            return ERROR_RESPONSE

    # Query N midgards -> pass data to handler -> compare results -> consensus or not