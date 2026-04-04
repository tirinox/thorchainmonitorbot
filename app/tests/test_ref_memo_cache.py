from collections import defaultdict
from fnmatch import fnmatch
from typing import cast

import pytest

from api.aionode.connector import ThorConnector
from api.aionode.types import ThorException, ThorMemoReference
from jobs.ref_memo_cache import RefMemoCache
from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.tx import NativeThorTx
from lib.db import DB
from lib.depcont import DepContainer


REFERENCE_TX_HASH = 'C757C9EE79A7341817017D0EA714E3CD5C9C366D2C7B1583631046E266A03347'
REFERENCE_MEMO = 'REFERENCE:BTC.BTC:=:ETH.USDT:0xE9fbf0857a16805535588fd018fb9C2Df1c5b0d5:491625094752/1/0:sto:0'
NORMAL_MEMO = '=:BTC.BTC:thor1dest:1000'


class FakeRedis:
    def __init__(self):
        self.hashes = defaultdict(dict)
        self.strings = {}
        self.expirations = {}

    async def hset(self, name, *args, mapping=None):
        bucket = self.hashes[name]
        if mapping is not None:
            for k, v in mapping.items():
                bucket[k] = v
            return len(mapping)
        if len(args) == 2:
            field, value = args
            bucket[field] = value
            return 1
        raise TypeError('Unsupported hset call')

    async def hget(self, name, field):
        return self.hashes.get(name, {}).get(field)

    async def hgetall(self, name):
        return dict(self.hashes.get(name, {}))

    async def set(self, name, value):
        self.strings[name] = value
        return True

    async def get(self, name):
        return self.strings.get(name)

    async def expire(self, name, seconds):
        self.expirations[name] = int(seconds)
        return 1

    async def keys(self, pattern):
        all_keys = list(self.hashes.keys()) + list(self.strings.keys())
        return [key for key in all_keys if fnmatch(key, pattern)]

    async def delete(self, *names):
        deleted = 0
        for name in names:
            if name in self.hashes:
                deleted += 1
            if name in self.strings:
                deleted += 1
            self.hashes.pop(name, None)
            self.strings.pop(name, None)
            self.expirations.pop(name, None)
        return deleted


class FakeDB:
    def __init__(self):
        self.redis = FakeRedis()

    async def get_redis(self):
        return self.redis


class FakeThorConnector:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def query_memo_reference(self, registration_hash: str):
        self.calls.append(registration_hash)
        if self.error:
            raise self.error
        return self.response


def make_tx(tx_hash: str, memo: str) -> NativeThorTx:
    return NativeThorTx(
        tx_hash=tx_hash,
        code=0,
        events=[],
        height=25621817,
        original={},
        signers=[],
        messages=[],
        memo=memo,
        timestamp=1_700_000_000,
    )


def make_block(*txs, block_no: int = 25621817) -> BlockResult:
    return BlockResult(
        block_no=block_no,
        txs=list(txs),
        end_block_events=[],
        begin_block_events=[],
        error=ScannerError(0, ''),
        timestamp=1_700_000_000,
    )


def make_cache(response=None, error=None) -> tuple[RefMemoCache, FakeThorConnector, FakeRedis]:
    deps = DepContainer()
    fake_db = FakeDB()
    fake_connector = FakeThorConnector(response=response, error=error)
    deps.db = cast(DB, cast(object, fake_db))
    deps.thor_connector = cast(ThorConnector, cast(object, fake_connector))
    cache = RefMemoCache(deps)
    return cache, fake_connector, fake_db.redis


def make_reference_payload() -> ThorMemoReference:
    return ThorMemoReference.from_json({
        'asset': 'BTC.BTC',
        'memo': '=:ETH.USDT:0xE9fbf0857a16805535588fd018fb9C2Df1c5b0d5:491625094752/1/0:sto:0',
        'reference': '11791',
        'height': '25621817',
        'registration_hash': REFERENCE_TX_HASH,
        'registered_by': 'thor1uszfy2dyd2rcjxxpy6wjuv450muljac6ssr70k',
        'used_by_txs': ['FFA1DA63BC81E7AEA8D094896739AE3D01FF60034A29E24AB81554C06C36476C'],
    })


def test_iter_reference_txs_only_returns_reference_memo_txs():
    block = make_block(
        make_tx(REFERENCE_TX_HASH, REFERENCE_MEMO),
        make_tx('normal-tx', NORMAL_MEMO),
    )

    found = list(RefMemoCache.iter_reference_txs(block))

    assert [tx.tx_hash for tx in found] == [REFERENCE_TX_HASH]


@pytest.mark.asyncio
async def test_on_data_queries_reference_and_caches_by_reference_id():
    response = make_reference_payload()
    cache, connector, redis = make_cache(response=response)

    await cache.on_data(None, make_block(make_tx(REFERENCE_TX_HASH, REFERENCE_MEMO)))

    assert connector.calls == [REFERENCE_TX_HASH]

    stored = await cache.get_by_reference_id(11791)
    assert stored == response
    assert await cache.get_memo(11791) == response.memo
    assert await cache.get_reference_id_by_registration_hash(REFERENCE_TX_HASH) == 11791
    ref_key = RefMemoCache.key_by_reference_id(11791)
    reg_key = RefMemoCache.key_by_registration_hash(REFERENCE_TX_HASH)
    assert ref_key in redis.strings
    assert redis.strings[reg_key] == '11791'
    assert redis.expirations[ref_key] == RefMemoCache.CACHE_TTL_SEC
    assert redis.expirations[reg_key] == RefMemoCache.CACHE_TTL_SEC


@pytest.mark.asyncio
async def test_on_data_deduplicates_repeated_block_processing():
    cache, connector, _redis = make_cache(response=make_reference_payload())
    block = make_block(make_tx(REFERENCE_TX_HASH, REFERENCE_MEMO))

    await cache.on_data(None, block)
    await cache.on_data(None, block)

    assert connector.calls == [REFERENCE_TX_HASH]


@pytest.mark.asyncio
async def test_on_data_does_not_cache_non_reference_memos():
    cache, connector, _redis = make_cache(response=make_reference_payload())

    await cache.on_data(None, make_block(make_tx('normal-tx', NORMAL_MEMO)))

    assert connector.calls == []
    assert await cache.get_by_reference_id(11791) is None


@pytest.mark.asyncio
async def test_on_data_skips_cache_write_when_lookup_fails():
    error = ThorException({
        'code': 3,
        'message': 'reference memo not found',
        'details': [],
    })
    cache, connector, _redis = make_cache(error=error)

    block = make_block(make_tx(REFERENCE_TX_HASH, REFERENCE_MEMO))
    await cache.on_data(None, block)
    await cache.on_data(None, block)

    assert connector.calls == [REFERENCE_TX_HASH, REFERENCE_TX_HASH]
    assert await cache.get_by_reference_id(11791) is None


@pytest.mark.asyncio
async def test_cache_reference_uses_separate_keys_per_reference_id():
    cache, _connector, redis = make_cache()

    ref_1 = make_reference_payload()
    ref_2 = ThorMemoReference.from_json({
        'asset': 'ETH.ETH',
        'memo': '=:BTC.BTC:bc1qdest:123/1/0:sto:0',
        'reference': '11792',
        'height': '25621818',
        'registration_hash': 'A757C9EE79A7341817017D0EA714E3CD5C9C366D2C7B1583631046E266A03348',
        'registered_by': 'thor1different',
        'used_by_txs': [],
    })

    await cache.cache_reference(ref_1)
    await cache.cache_reference(ref_2)

    ref_1_key = RefMemoCache.key_by_reference_id(11791)
    ref_2_key = RefMemoCache.key_by_reference_id(11792)
    assert ref_1_key in redis.strings
    assert ref_2_key in redis.strings
    assert ref_1_key != ref_2_key
    assert redis.expirations[ref_1_key] == RefMemoCache.CACHE_TTL_SEC
    assert redis.expirations[ref_2_key] == RefMemoCache.CACHE_TTL_SEC


