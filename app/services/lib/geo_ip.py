import asyncio
import json
from typing import List

from aiohttp import ClientError
from aioredis import Redis

from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger


class GeoIPManager:
    DB_KEY_IP_INFO = 'NodeIpGeoInfo'
    API_URL = 'https://ipapi.co/{address}/json/'

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.expire_period_sec = int(
            parse_timespan_to_seconds(deps.cfg.as_str('node_info.geo_ip.expire', default='24h')))
        self.logger = class_logger(self)

    def key(self, ip: str):
        return f'{self.DB_KEY_IP_INFO}:{ip}'

    async def get_ip_info_from_external_api(self, ip: str):
        url = self.API_URL.format(address=ip)
        try:
            async with self.deps.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return None
        except ClientError as e:
            self.logger.exception(f'GeoIP API error: {e}')
            return None

    async def get_ip_info_from_cached(self, ip: str):
        r: Redis = await self.deps.db.get_redis()
        raw_data = await r.get(self.key(ip))
        if raw_data:
            return json.loads(raw_data)

    async def _set_ip_info(self, ip, data):
        r: Redis = self.deps.db.redis
        await r.set(self.key(ip), json.dumps(data), ex=self.expire_period_sec)

    async def get_ip_info(self, ip: str, cached=True):
        if not ip or not isinstance(ip, str):
            return None

        if cached:
            cached_data = await self.get_ip_info_from_cached(ip)
            if cached_data:
                return cached_data

        data = await self.get_ip_info_from_external_api(ip)

        if cached and data:
            await self._set_ip_info(ip, data)

        return data

    async def get_ip_info_bulk(self, ip_list: List[str], cached=True):
        return await asyncio.gather(*(self.get_ip_info(ip, cached) for ip in ip_list))
