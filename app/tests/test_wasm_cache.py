from types import SimpleNamespace
from typing import cast

import pytest

from api.aionode.connector import ThorConnector
from jobs.fetch.cached.wasm import WasmCache
from lib.db import DB


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.values = {}

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, field=None, value=None, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if mapping is not None:
            bucket.update(mapping)
        elif field is not None:
            bucket[field] = value

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.values[key] = value


class FakeConnector:
    """Serves the cosmwasm endpoints WasmCache needs and records which contracts were queried."""

    def __init__(self, contracts_by_code: dict, failing: set = frozenset()):
        self.contracts_by_code = contracts_by_code
        self.failing = set(failing)
        self.info_queries = []

    async def query_raw(self, path):
        if path.startswith('/cosmwasm/wasm/v1/code?'):
            return {'code_infos': [{'code_id': str(c)} for c in self.contracts_by_code], 'pagination': {}}
        if path.startswith('/cosmwasm/wasm/v1/code/'):
            code_id = int(path.split('/')[5])
            return {'contracts': self.contracts_by_code[code_id], 'pagination': {}}
        if path.startswith('/cosmwasm/wasm/v1/contract/'):
            address = path.rsplit('/', 1)[1]
            self.info_queries.append(address)
            if address in self.failing:
                raise ConnectionError('node is down')
            return {'address': address, 'contract_info': {
                'label': f'label-{address}',
                'created': {'block_height': '100'},
            }}
        raise AssertionError(f'unexpected path {path}')


def make_cache(connector: FakeConnector, redis: FakeRedis) -> WasmCache:
    cache = WasmCache(cast(ThorConnector, cast(object, connector)),
                      db=cast(DB, cast(object, SimpleNamespace(get_redis=lambda: _async(redis)))))
    cache.INTER_REQUEST_SLEEP = 0
    return cache


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_refresh_fetches_only_contracts_it_has_not_seen():
    redis = FakeRedis()
    connector = FakeConnector({1: ['a', 'b'], 2: ['c']})
    await make_cache(connector, redis).get()
    assert sorted(connector.info_queries) == ['a', 'b', 'c']

    # the daily snapshot expired and a contract was instantiated since
    redis.values.clear()
    connector.contracts_by_code[2].append('d')
    connector.info_queries.clear()

    stats = await make_cache(connector, redis).get()

    assert connector.info_queries == ['d']
    assert stats.total_contracts == 4
    assert stats.find_label('a') == 'label-a'
    assert len(stats.new_contracts_since_block(100)) == 4  # creation blocks come back from Redis too


@pytest.mark.asyncio
async def test_failed_contract_fetch_is_retried_on_next_refresh():
    redis = FakeRedis()
    connector = FakeConnector({1: ['a', 'b']}, failing={'b'})
    stats = await make_cache(connector, redis).get()
    assert stats.find_label('b') == ''

    redis.values.clear()
    connector.failing.clear()
    connector.info_queries.clear()

    stats = await make_cache(connector, redis).get()

    assert connector.info_queries == ['b']
    assert stats.find_label('b') == 'label-b'
