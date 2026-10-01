import json
from types import SimpleNamespace

import pytest

from lib.config import Config
from lib.geo_ip import GeoIPManager
from tests.fakes import FakeDB, FakeRedis
from web_api import AppSettingsAPI


class CountingRedis(FakeRedis):
    def __init__(self):
        super().__init__()
        self.requests = 0

    async def get(self, name):
        self.requests += 1
        return await super().get(name)

    async def mget(self, keys):
        self.requests += 1
        return await super().mget(keys)


def _make_api():
    # skip __init__: it needs a config file and Redis
    api = AppSettingsAPI.__new__(AppSettingsAPI)
    api.deps = SimpleNamespace(cfg=Config(data={}), db=FakeDB(CountingRedis()))
    return api


async def _get(api, ip):
    resp = await api._get_node_ip_info(SimpleNamespace(path_params={'ip': ip}))
    return resp.status_code, json.loads(resp.body)


def test_parse_ip_list():
    parse = AppSettingsAPI._parse_ip_list
    assert parse('1.2.3.4, 5.6.7.8,1.2.3.4') == ['1.2.3.4', '5.6.7.8']
    assert parse('2001:db8::1') == ['2001:db8::1']
    assert parse('foo,,1.2.3.4,999.1.1.1,*') == ['1.2.3.4']
    assert parse('1.1.1.1,' * 500) == ['1.1.1.1']  # repeats are one address

    with pytest.raises(ValueError):
        parse(','.join(f'10.0.{i // 256}.{i % 256}' for i in range(AppSettingsAPI.IP_MAX_COUNT + 1)))
    with pytest.raises(ValueError):
        parse('1,' * 100_000)


@pytest.mark.asyncio
async def test_node_ip_info_is_one_redis_request():
    api = _make_api()
    redis = api.deps.db.redis
    await redis.set(GeoIPManager(api.deps).key('1.2.3.4'), json.dumps({'country': 'NL'}))

    ips = ['1.2.3.4'] + [f'10.0.0.{i}' for i in range(200)]
    code, body = await _get(api, ','.join(ips))

    assert code == 200
    assert body['1.2.3.4'] == {'country': 'NL'} and body['10.0.0.7'] is None
    assert len(body) == len(ips)
    assert redis.requests == 1


@pytest.mark.asyncio
async def test_node_ip_info_refuses_a_flood():
    api = _make_api()

    code, body = await _get(api, '1,' * 100_000)
    assert code == 400 and 'error' in body

    code, body = await _get(api, 'not-an-ip')
    assert body == {'error': 'not-found'}
    assert api.deps.db.redis.requests == 0
