import asyncio
import json
import logging
from typing import List

from aiohttp import ClientError
from aioredis import Redis

from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer

import re


class GeoIPManager:
    DB_KEY_IP_INFO = 'NodeIpGeoInfo'
    API_URL = 'https://ipapi.co/{address}/json/'

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.expire_period_sec = int(
            parse_timespan_to_seconds(deps.cfg.as_str('node_info.geo_ip.expire', default='24h')))
        self.logger = logging.getLogger(self.__class__.__name__)

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

    async def get_ip_info(self, ip: str, cached=True):
        if not ip or not isinstance(ip, str):
            return None

        if cached:
            r: Redis = await self.deps.db.get_redis()
            raw_data = await r.get(self.key(ip))
            if raw_data:
                return json.loads(raw_data)

        data = await self.get_ip_info_from_external_api(ip)

        if cached and data:
            await r.set(self.key(ip), json.dumps(data), expire=self.expire_period_sec)

        return data

    async def get_ip_info_bulk(self, ip_list: List[str], cached=True):
        return await asyncio.gather(*(self.get_ip_info(ip, cached) for ip in ip_list))

    @staticmethod
    def get_general_provider(data: dict):
        org = data.get('org', '')
        components = re.split('[ -]', org)
        if components:
            return str(components[0]).upper()
        return org
