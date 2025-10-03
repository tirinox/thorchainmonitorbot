from typing import Union, Optional, List

import aiohttp

from api.aionode.nodeclient import ThorNodeClient
from api.midgard.parser import MidgardParserV2, TxParseResult
from api.midgard.urlgen import free_url_gen
from lib.constants import HTTP_CLIENT_ID
from lib.logs import WithLogger
from models.earnings_history import EarningHistoryResponse
from models.pool_info import PoolInfoMap
from models.pool_member import PoolMemberDetails
from models.swap_history import SwapHistoryResponse

DEFAULT_MIDGARD_PORT = 8080


class MidgardConnector(WithLogger):
    ERROR_RESPONSE = 'ERROR_Midgard'
    ERROR_NOT_FOUND = 'NotFound_Midgard'
    ERROR_NO_CLIENT = 'ERROR_NoClient'

    def __init__(self, session: aiohttp.ClientSession, retry_number=3, public_url='', network_id=None):
        super().__init__()

        self._public_url = public_url

        self.public_url = public_url
        self.session = session
        self.retries = retry_number
        self.session = session or aiohttp.ClientSession()
        self.urlgen = free_url_gen
        self.parser = MidgardParserV2(network_id)

    @property
    def public_url(self):
        return self._public_url

    @public_url.setter
    def public_url(self, value):
        self._public_url = value.rstrip('/')
        self.logger.info(f"Midgard public URL set to {value}")

    async def _request_json_from_midgard_by_ip(self, ip_address: str, path: str):
        path = path.lstrip('/')

        if ip_address == self.public_url:
            full_url = f'{self.public_url}/{path}'
        else:
            port = DEFAULT_MIDGARD_PORT
            full_url = f'http://{ip_address}:{port}/{path}'

        self.logger.info(f"Getting Midgard endpoint: {full_url}")
        try:
            headers = {ThorNodeClient.HEADER_CLIENT_ID: HTTP_CLIENT_ID}
            async with self.session.get(full_url, headers=headers) as resp:
                self.logger.debug(f'Midgard "{full_url}"; result code = {resp.status}.')

                if resp.status == 404:
                    return self.ERROR_NOT_FOUND
                elif resp.status != 200:
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

    # noinspection PyTypeChecker
    async def request(self, path: str) -> Union[str, dict, list]:
        result = await self._request_json_from_midgard_by_ip(self.public_url, path)
        if isinstance(result, str) and result != self.ERROR_NOT_FOUND:
            self.logger.error(f'Probably there is an issue. Midgard has returned a plain string: {result!r} '
                              f'for the path {path!r}')
        else:
            return result

    async def query_earnings(self, from_ts=0, to_ts=0, count=0, interval='') -> Optional[EarningHistoryResponse]:
        url = self.urlgen.url_for_earnings_history(from_ts, to_ts, count, interval)
        j = await self.request(url)
        if j:
            return EarningHistoryResponse.from_json(j)

    async def query_swap_stats(self, from_ts=0, to_ts=0, count=10, interval='day', pool=None) \
            -> Optional[SwapHistoryResponse]:
        url = self.urlgen.url_for_swap_history(from_ts, to_ts, count, interval, pool)
        j = await self.request(url)
        if j:
            return SwapHistoryResponse.from_json(j)

    async def query_transactions(self, url_for_tx) -> Optional[TxParseResult]:
        j = await self.request(url_for_tx)
        if j:
            return self.parser.parse_tx_response(j)

    async def query_pool_membership(self, address: str) -> List[PoolMemberDetails]:
        j = await self.request(
            self.urlgen.url_for_address_pool_membership(address)
        )
        if j == self.ERROR_RESPONSE or j == self.ERROR_NOT_FOUND:
            return []
        else:
            return self.parser.parse_pool_membership(j)

    async def query_pools(self, period: str = '30d', parse=True) -> Optional[PoolInfoMap]:
        raw_data = await self.request(self.urlgen.url_pool_info(period=period))
        if not raw_data or raw_data == self.ERROR_RESPONSE:
            return None
        return self.parser.parse_pool_info(raw_data) if parse else raw_data

    async def query_affiliates(self, count=14, interval='day'):
        j = await self.request(
            self.urlgen.url_affiliate_history(count=count, interval=interval)
        )
        if j and j != self.ERROR_RESPONSE:
            return self.parser.parse_affiliate_history(j)

    async def query_pool_depth_history(self, pool: str, count=30, interval='day'):
        j = await self.request(
            self.urlgen.url_pool_depth_history(pool, count=count, interval=interval)
        )
        if j and j != self.ERROR_RESPONSE:
            return self.parser.parse_pool_depth_history(j)