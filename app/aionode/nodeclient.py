import logging

import ujson
from aiohttp import ClientSession, ClientTimeout
from aiohttp.helpers import sentinel

from aionode.env import ThorEnvironment


class ThorNodeClient:
    HEADER_CLIENT_ID = 'X-Client-ID'

    def __init__(self, session: ClientSession, env: ThorEnvironment, logger=None, extra_headers=None):
        self.session = session
        self.timeout = ClientTimeout(total=env.timeout) if env.timeout else sentinel
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.extra_headers = extra_headers
        self.env = env

    async def request(self, path, is_rpc=False):
        url = self.connection_url(path, is_rpc)
        self.logger.debug(f'Node GET "{url}"')
        async with self.session.get(url, timeout=self.timeout, headers=self.extra_headers) as resp:
            self.logger.debug(f'Node RESPONSE "{url}" code={resp.status}')
            if resp.status == 404:
                raise FileNotFoundError(f'{url} not found, sorry!')
            elif resp.status == 501:
                raise NotImplementedError(f'{url} not implemented, sorry!')
            text = await resp.text()
            return ujson.loads(text)

    def set_client_id_header(self, client_id: str):
        if not isinstance(self.extra_headers, dict):
            self.extra_headers = {}

        if not client_id:
            del self.extra_headers[self.HEADER_CLIENT_ID]
        else:
            self.extra_headers[self.HEADER_CLIENT_ID] = client_id

    def __repr__(self) -> str:
        return f'ThorNodeClient({self.env.thornode_url!r})'

    def connection_url(self, path, is_rpc):
        if is_rpc:
            return f'{self.env.rpc_url}{path}'
        else:
            return f'{self.env.thornode_url}{path}'
