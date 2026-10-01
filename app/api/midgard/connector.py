import asyncio
from typing import Union, Optional, List

import aiohttp

from api.aionode.nodeclient import ThorNodeClient
from api.aionode.types import ThorPool
from api.midgard.parser import MidgardParserV2, TxParseResult
from api.midgard.urlgen import free_url_gen
from lib.constants import HTTP_CLIENT_ID
from lib.logs import WithLogger
from models.earnings_history import EarningHistoryResponse
from models.pool_info import PoolInfoMap, PoolInfo, PoolInfoHistoricEntry
from models.pool_member import PoolMemberDetails
from models.swap_history import SwapHistoryResponse

DEFAULT_MIDGARD_PORT = 8080


class MidgardError(Exception):
    """Midgard gave no usable answer: a network failure, a bad status, or a body that is not JSON."""


class MidgardNotFound(MidgardError):
    """404: Midgard is fine, there is just nothing at this path (no such THORName, member, pool...)."""


class MidgardBadResponse(MidgardError):
    def __init__(self, status: int, url: str, body: str = ''):
        super().__init__(f'Midgard answered {status} for {url}: {body!r}')
        self.status = status
        self.url = url

    @property
    def is_temporary(self):
        # the request itself is fine, Midgard may answer the next time
        return self.status >= 500 or self.status == 429


class MidgardConnector(WithLogger):
    def __init__(self, session: aiohttp.ClientSession, retry_number=3, public_url='', network_id=None,
                 retry_delay=1.0):
        super().__init__()

        self._public_url = public_url

        self.public_url = public_url
        self.retries = max(1, int(retry_number))
        self.retry_delay = retry_delay
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
        """One attempt. Returns the parsed JSON or raises a MidgardError."""
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
                    raise MidgardNotFound(full_url)
                elif resp.status != 200:
                    raise MidgardBadResponse(resp.status, full_url, (await resp.text())[:200])
                return await resp.json()
        except MidgardError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            # ValueError: the body is not JSON
            raise MidgardError(f'Midgard request to {full_url} failed: {e!r}') from e

    async def request(self, path: str) -> Union[dict, list]:
        """
        Midgard's JSON answer for the path.
        Raises MidgardNotFound on 404 and another MidgardError when Midgard cannot answer;
        temporary failures (network, 5xx, 429) are tried `retries` times first.
        """
        for attempt in range(1, self.retries + 1):
            try:
                return await self._request_json_from_midgard_by_ip(self.public_url, path)
            except MidgardNotFound:
                raise
            except MidgardError as e:
                is_temporary = not isinstance(e, MidgardBadResponse) or e.is_temporary
                if not is_temporary or attempt == self.retries:
                    self.logger.error(f'{e} (attempt {attempt}/{self.retries}, giving up)')
                    raise
                self.logger.warning(f'{e} (attempt {attempt}/{self.retries}, retrying)')
                await asyncio.sleep(self.retry_delay * attempt)

    async def query_earnings(self, from_ts=0, to_ts=0, count=0, interval='') -> Optional[EarningHistoryResponse]:
        url = self.urlgen.url_for_earnings_history(from_ts, to_ts, count, interval)
        j = await self.request(url)
        if j:
            return EarningHistoryResponse.from_json(j)

    async def query_last_aggregated_ts(self) -> int:
        """
        Timestamp of the last block that is in Midgard's aggregates; history after it is not complete yet.
        """
        try:
            j = await self.request(self.urlgen.url_health())
        except MidgardError:
            return 0  # unknown: the caller takes it for "nothing is aggregated yet"
        if not isinstance(j, dict):
            return 0
        return int((j.get('lastAggregated') or {}).get('timestamp') or 0)

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
        try:
            j = await self.request(self.urlgen.url_for_address_pool_membership(address))
        except MidgardNotFound:
            return []  # the address is not a member of any pool
        return self.parser.parse_pool_membership(j)

    async def query_pools(self, period: str = '30d', parse=True) -> Optional[PoolInfoMap]:
        raw_data = await self.request(self.urlgen.url_pools_info(period=period))
        if not raw_data:
            return None
        return self.parser.parse_pool_info(raw_data) if parse else raw_data

    async def query_pool(self, pool: str, period: str = '30d', parse=True) -> Optional[PoolInfo]:
        try:
            raw_data = await self.request(self.urlgen.url_pool_info(pool, period=period))
        except MidgardNotFound:
            return None  # no such pool
        if not raw_data:
            return None
        return PoolInfo.from_midgard_json(raw_data) if parse else raw_data

    async def query_affiliates(self, count=14, interval='day', from_ts=0, to_ts=0):
        j = await self.request(
            self.urlgen.url_affiliate_history(from_ts, to_ts, count=count, interval=interval)
        )
        if j:
            return self.parser.parse_affiliate_history(j)

    async def query_pool_depth_history(self, pool: str, count=30, interval='day'):
        j = await self.request(
            self.urlgen.url_pool_depth_history(pool, count=count, interval=interval)
        )
        if j:
            return self.parser.parse_pool_depth_history(j)

    async def query_pool_depth_at(self, pool: str, ts) -> Optional[PoolInfoHistoricEntry]:
        """
        Pool depths at the end of the 5-min interval that contains ts (Midgard's finest resolution).
        """
        try:
            j = await self.request(self.urlgen.url_pool_depth_at(pool, ts))
        except MidgardNotFound:
            return None  # no such pool
        if isinstance(j, dict):
            intervals = self.parser.parse_pool_depth_history(j).intervals
            return intervals[-1] if intervals else None