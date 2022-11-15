import aiohttp
from aiothornode.connector import ThorConnector

from services.lib.utils import class_logger

DEFAULT_MIDGARD_PORT = 8080


class MidgardConnector:
    ERROR_RESPONSE = 'ERROR_Midgard'
    ERROR_NO_CLIENT = 'ERROR_NoClient'

    def __init__(self, session: aiohttp.ClientSession,
                 thor: ThorConnector,
                 retry_number=3,
                 public_url='',
                 use_nodes=True):
        self.logger = class_logger(self)
        self.thor = thor
        self.public_url = public_url.rstrip('/')
        self.use_nodes = use_nodes
        self.session = session
        self.retries = retry_number
        self.session = session or aiohttp.ClientSession()

    async def _request_json_from_midgard_by_ip(self, ip_address: str, path: str):
        path = path.lstrip('/')

        if ip_address == self.public_url:
            full_url = f'{self.public_url}/{path}'
        else:
            port = DEFAULT_MIDGARD_PORT
            full_url = f'http://{ip_address}:{port}/{path}'

        self.logger.info(f"Getting Midgard endpoint: {full_url}")
        try:
            async with self.session.get(full_url) as resp:
                self.logger.debug(f'Midgard "{full_url}"; result code = {resp.status}.')
                if resp.status != 200:
                    try:
                        answer = resp.content[:200]
                    except TypeError:
                        answer = 'unknown'
                    self.logger.warning(f'Midgard ({full_url}) BAD response {resp.status = }, "{answer}"!')
                    return self.ERROR_RESPONSE
                j = await resp.json()
                return j
        except Exception as e:
            self.logger.error(f'Midgard ({ip_address}/{path}) exception: {e!r}.')
            return self.ERROR_RESPONSE

    async def request(self, path: str):
        return await self._request_json_from_midgard_by_ip(self.public_url, path)
