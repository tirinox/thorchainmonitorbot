import logging
from typing import Optional, Dict, List

import ujson
from aiohttp import ClientSession, ClientTimeout
from aiohttp.helpers import sentinel

from api.aionode.env import ThorEnvironment


class ThorNodeClient:
    HEADER_CLIENT_ID = 'X-Client-ID'

    def __init__(self, session: ClientSession, env: ThorEnvironment, logger=None, extra_headers=None):
        self.session = session
        self.timeout = ClientTimeout(total=env.timeout) if env.timeout else sentinel
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.extra_headers = extra_headers
        self.env = env

    async def request(self, path, is_rpc=False, height: Optional[int] = None) -> Dict:
        url = self.connection_url(path, is_rpc)

        params = {}
        if height is not None:
            params['height'] = height

        self.logger.debug(f'Node GET "{url}"')
        async with self.session.get(url, timeout=self.timeout, headers=self.extra_headers, params=params) as resp:
            self.logger.debug(f'Node RESPONSE ({resp.status}) "{url}"')
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
        base_url = self.env.rpc_url if is_rpc else self.env.thornode_url
        return f'{base_url.rstrip("/")}/{path.lstrip("/")}'

    async def paginated_request(self,
                                path: str,
                                height: Optional[int] = None,
                                limit: int = 1000,
                                extra_params: Optional[Dict[str, str]] = None,
                                result_key: str = ""
                                ) -> List[Dict]:
        """
        Fetch all paginated results from a Cosmos SDK REST API endpoint.

        Args:
            session (aiohttp.ClientSession): aiohttp session to use.
            base_url (str): Host address (e.g. http://1.2.3.4:1317)
            path (str): REST endpoint path starting with '/', e.g. '/cosmos/bank/v1beta1/denom_owners/xrp-xrp'
            height (Optional[int]): Optional block height to query.
            limit (int): Number of items per page (max typically 1000).
            extra_params (Optional[Dict[str, str]]): Extra query parameters.
            result_key (str): The JSON key under which results are listed (e.g., 'denom_owners').

        Returns:
            List[Dict]: Combined list of all paginated results.
        """
        full_url = self.connection_url(path, is_rpc=False)
        results = []
        next_key = None
        params = extra_params.copy() if extra_params else {}

        if height is not None:
            params["height"] = str(height)

        params["pagination.limit"] = str(limit)

        while True:
            if next_key:
                params["pagination.key"] = next_key

            self.logger.debug(f'Node GET "{full_url}"')
            async with self.session.get(full_url, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Failed to fetch paginated results: {resp.status} {text}")
                data = await resp.json()

                page_items = data.get(result_key, [])
                results.extend(page_items)
                next_key = data.get("pagination", {}).get("next_key")

                if not next_key:
                    break

        return results
