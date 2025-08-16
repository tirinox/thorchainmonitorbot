import json
from typing import List

from aiohttp import ClientError
from redis.asyncio import Redis

from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import parallel_run_in_groups


class GeoIPManager(WithLogger):
    DB_KEY_IP_INFO = 'NodeIpGeoInfo'
    API_URL = 'https://ipapi.co/{address}/json/'
    PARALLEL_FETCH_GROUP_SIZE = 8

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.expire_period_sec = int(
            parse_timespan_to_seconds(deps.cfg.as_str('node_info.geo_ip.expire', default='24h')))

    def key(self, ip: str):
        return f'{self.DB_KEY_IP_INFO}:{ip}'

    async def get_ip_info_from_external_api(self, ip: str):
        cooldown = Cooldown(self.deps.db, 'GeoIP-Rate-Limit', 60)
        try:
            if not await cooldown.can_do():
                self.logger.debug(f'GeoIP is on cooldown. I will not even try!')
                return None

            url = self.API_URL.format(address=ip)

            self.logger.info(f"Request GeoIP API: {url}")

            async with self.deps.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    self.logger.error(f'GeoIP API rate limit exceeded. Cooldown: {cooldown.cooldown} sec')
                    await cooldown.do()
                    return None
                else:
                    return None
        except ClientError as e:
            self.logger.exception(f'GeoIP API error: {e}')
            return None

    async def get_ip_info_from_cache(self, ip: str):
        if not ip:
            return
        r: Redis = await self.deps.db.get_redis()
        raw_data = await r.get(self.key(ip))
        if raw_data:
            return json.loads(raw_data)

    async def clear_info(self, ip: str):
        if not ip:
            return
        await self.deps.db.redis.delete(self.key(ip))

    async def _set_ip_info(self, ip, data):
        r: Redis = self.deps.db.redis
        await r.set(self.key(ip), json.dumps(data), ex=self.expire_period_sec)

    async def get_ip_info(self, ip: str, cached=True):
        if not ip or not isinstance(ip, str):
            return None

        if cached:
            cached_data = await self.get_ip_info_from_cache(ip)
            if cached_data:
                return cached_data

        data = await self.get_ip_info_from_external_api(ip)

        if cached:
            if data:
                await self._set_ip_info(ip, data)
            else:
                self.logger.warning(f'No data could be fetched for IP: {ip}.')

        return data

    async def get_ip_info_bulk(self, ip_list: List[str], cached=True):
        tasks = [self.get_ip_info(ip, cached) for ip in ip_list]
        return await parallel_run_in_groups(tasks, group_size=self.PARALLEL_FETCH_GROUP_SIZE)

    async def get_ip_info_bulk_as_dict(self, ip_list: List[str], cached=True):
        ip_set = set(ip for ip in ip_list if ip)
        ip_keys = list(ip_set)
        ip_info_list = await self.get_ip_info_bulk(ip_keys, cached)
        return {
            ip: info for ip, info in zip(ip_keys, ip_info_list)
        }
