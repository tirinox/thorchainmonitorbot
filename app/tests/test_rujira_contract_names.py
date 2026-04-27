import json
from pathlib import Path
from typing import cast

import pytest
from aiohttp import ClientSession

from jobs.fetch.cached.wasm import WasmCache
from jobs.fetch.cached.rujira_contract_names import RujiraContractNameCache
from jobs.fetch.wasm_stats import WasmStatsBuilder
from jobs.wasm_recorder import CosmWasmRecorder
from lib.db import DB
from models.wasm import WasmTopContract


TEST_PAYLOAD = {
    'families': {
        'family-a': {
            'name': 'Family A',
            'product': 'Product A',
        },
        'family-b': {
            'product': 'Product B',
        },
    },
    'addresses': {
        'thor1name': {
            'family': 'family-a',
            'name': 'Readable Name',
            'contractLabel': 'raw:label',
        },
        'thor1product': {
            'family': 'family-b',
            'contractLabel': 'raw:product',
        },
        'thor1slug': {
            'family': 'missing-family',
            'contractName': 'rujira-ghost-credit',
        },
    },
}

REAL_JSON_PATH = (
    Path(__file__).resolve().parent.parent / 'data' / 'rujira' / 'rujira-mainnet.json'
)


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else TEST_PAYLOAD

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def text(self):
        return json.dumps(self.payload)


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response = response or FakeResponse()
        self.exc = exc
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if self.exc is not None:
            raise self.exc
        return self.response


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value
        return True


class FakeDB:
    def __init__(self):
        self.redis = FakeRedis()

    async def get_redis(self):
        return self.redis


class StubWasmCache:
    async def get_label(self, address: str) -> str:
        return 'rujira-ghost-credit'


class StubRecorder:
    async def get_all_contracts_calls_totals(self, period_start, now):
        return {'thor1contract': 321}

    async def get_contract_unique_users(self, address, days: int):
        return 17


class StubNameCache:
    async def resolve_name(self, address: str, fallback: str = '') -> str:
        return 'Friendly readable contract title'


def test_extract_names_from_payload_uses_best_available_name():
    mapping = RujiraContractNameCache.extract_names_from_payload(TEST_PAYLOAD)

    assert mapping['thor1name'] == 'Readable Name'
    assert mapping['thor1product'] == 'Product B'
    assert mapping['thor1slug'] == 'rujira ghost credit'


def test_extract_names_from_real_repo_payload():
    payload = json.loads(REAL_JSON_PATH.read_text(encoding='utf-8'))

    mapping = RujiraContractNameCache.extract_names_from_payload(payload)

    assert mapping
    assert mapping['thor1yqf5spdv8c4088zmvqsg32eq63fzepsjvntahdk0ek0yjnkt3qdqftp3lc'] == 'RJI - The Rujira Index'


@pytest.mark.asyncio
async def test_load_falls_back_to_local_file_and_persists_to_redis(tmp_path):
    local_file = tmp_path / 'rujira-mainnet.json'
    local_file.write_text(json.dumps(TEST_PAYLOAD), encoding='utf-8')

    db = FakeDB()
    cache = RujiraContractNameCache(
        session=cast(ClientSession, cast(object, FakeSession(response=FakeResponse(status=503)))),
        db=cast(DB, cast(object, db)),
        local_file=local_file,
    )

    mapping = await cache.get(forced=True)

    assert mapping['thor1name'] == 'Readable Name'
    assert json.loads(db.redis.values[RujiraContractNameCache.REDIS_KEY])['thor1product'] == 'Product B'


@pytest.mark.asyncio
async def test_load_falls_back_to_redis_when_remote_and_local_are_unavailable(tmp_path):
    db = FakeDB()
    db.redis.values[RujiraContractNameCache.REDIS_KEY] = json.dumps({'thor1cached': 'Cached Name'})

    cache = RujiraContractNameCache(
        session=cast(ClientSession, cast(object, FakeSession(exc=RuntimeError('network down')))),
        db=cast(DB, cast(object, db)),
        local_file=tmp_path / 'missing.json',
    )

    mapping = await cache.get(forced=True)

    assert mapping == {'thor1cached': 'Cached Name'}


@pytest.mark.asyncio
async def test_wasm_stats_builder_uses_friendly_truncated_display_name():
    builder = WasmStatsBuilder(
        wasm_cache=cast(WasmCache, cast(object, StubWasmCache())),
        recorder=cast(CosmWasmRecorder, cast(object, StubRecorder())),
        contract_name_cache=cast(RujiraContractNameCache, cast(object, StubNameCache())),
        top_label_limit=12,
    )

    top_contracts = await builder._build_top_contracts(0, 1, top_n=10, days=7)

    assert len(top_contracts) == 1
    assert top_contracts[0].label == 'rujira-ghost-credit'
    assert top_contracts[0].display_label == 'Friendly re…'


def test_wasm_top_contract_serialization_preserves_display_label():
    contract = WasmTopContract(
        address='thor1contract',
        label='raw:label',
        calls=12,
        unique_users=3,
        display_label='Readable Label',
    )

    restored = WasmTopContract.from_dict(contract.to_dict())

    assert restored == contract
