from typing import cast

import pytest

from api.aionode.connector import ThorConnector
from api.aionode.types import ThorException, ThorMemoReference
from jobs.ref_memo_cache import RefMemoCache, ReferenceMemoCandidate
from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.tx import NativeThorTx, ThorTxMessage, ThorMessageType
from lib.db import DB
from lib.depcont import DepContainer
from tests.fakes import FakeDB, FakeRedis


REFERENCE_TX_HASH = 'C757C9EE79A7341817017D0EA714E3CD5C9C366D2C7B1583631046E266A03347'
REFERENCE_MEMO = 'REFERENCE:BTC.BTC:=:ETH.USDT:0xE9fbf0857a16805535588fd018fb9C2Df1c5b0d5:491625094752/1/0:sto:0'
NORMAL_MEMO = '=:BTC.BTC:thor1dest:1000'

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


def make_deposit_tx(tx_hash: str, memo: str, asset: str = 'BTC.BTC', amount: int = 100_000_000) -> NativeThorTx:
    msg = ThorTxMessage.from_dict({
        '@type': ThorMessageType.MsgDeposit.value,
        'coins': [{'asset': asset, 'amount': str(amount)}],
        'signer': 'thor1alice',
        'memo': memo,
    })
    return NativeThorTx(
        tx_hash=tx_hash,
        code=0,
        events=[],
        height=25621817,
        original={},
        signers=[],
        messages=[msg],
        memo=memo,
        timestamp=1_700_000_000,
    )


def make_observed_quorum_tx(tx_id: str, memo: str, is_inbound: bool = True) -> NativeThorTx:
    msg = ThorTxMessage.from_dict({
        '@type': ThorMessageType.MsgObservedTxQuorum.value,
        'quoTx': {
            'obsTx': {
                'tx': {
                    'id': tx_id,
                    'chain': 'ETH',
                    'from_address': '0xfoo',
                    'to_address': 'thor1vault',
                    'coins': [{'asset': 'ETH.ETH', 'amount': '1000', 'decimals': '8'}],
                    'gas': [],
                    'memo': memo,
                },
                'status': 'incomplete',
                'out_hashes': [],
                'block_height': '25621817',
                'finalise_height': '25621817',
                'aggregator': '',
                'aggregator_target': '',
                'aggregator_target_limit': None,
            },
            'inbound': is_inbound,
        },
    })
    return NativeThorTx(
        tx_hash=f'native-{tx_id}',
        code=0,
        events=[],
        height=25621817,
        original={},
        signers=[],
        messages=[msg],
        memo='',
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


def test_iter_reference_candidates_from_deposit():
    deposit = make_deposit_tx(REFERENCE_TX_HASH, REFERENCE_MEMO)
    block = make_block(deposit)

    candidates = list(RefMemoCache.iter_reference_candidates(block))
    assert len(candidates) == 1
    assert candidates[0] == ReferenceMemoCandidate(REFERENCE_TX_HASH, REFERENCE_MEMO, 'native_deposit')


def test_iter_reference_candidates_from_observed_inbound():
    obs_tx_id = 'A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2'
    block = make_block(make_observed_quorum_tx(obs_tx_id, REFERENCE_MEMO, is_inbound=True))

    candidates = list(RefMemoCache.iter_reference_candidates(block))
    assert len(candidates) == 1
    assert candidates[0].registration_hash == obs_tx_id
    assert candidates[0].source == 'observed_in'


def test_iter_reference_candidates_ignores_outbound_observed():
    obs_tx_id = 'A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2'
    block = make_block(make_observed_quorum_tx(obs_tx_id, REFERENCE_MEMO, is_inbound=False))

    candidates = list(RefMemoCache.iter_reference_candidates(block))
    assert candidates == []


def test_iter_reference_candidates_ignores_non_reference_memos():
    deposit = make_deposit_tx('some-hash', NORMAL_MEMO)
    block = make_block(deposit)

    candidates = list(RefMemoCache.iter_reference_candidates(block))
    assert candidates == []


@pytest.mark.asyncio
async def test_on_data_queries_reference_and_caches_by_reference_id():
    response = make_reference_payload()
    cache, connector, redis = make_cache(response=response)

    await cache.on_data(None, make_block(make_deposit_tx(REFERENCE_TX_HASH, REFERENCE_MEMO)))

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
    block = make_block(make_deposit_tx(REFERENCE_TX_HASH, REFERENCE_MEMO))

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

    block = make_block(make_deposit_tx(REFERENCE_TX_HASH, REFERENCE_MEMO))
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


@pytest.mark.asyncio
async def test_on_data_processes_deposit_reference_tx():
    response = make_reference_payload()
    cache, connector, redis = make_cache(response=response)

    deposit = make_deposit_tx(REFERENCE_TX_HASH, REFERENCE_MEMO)
    block = make_block(deposit)

    await cache.on_data(None, block)

    assert connector.calls == [REFERENCE_TX_HASH]
    assert await cache.get_memo(11791) == response.memo
    assert await cache.get_reference_id_by_registration_hash(REFERENCE_TX_HASH) == 11791


@pytest.mark.asyncio
async def test_on_data_processes_observed_inbound_reference_tx():
    obs_tx_id = 'A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2'
    observed_response = ThorMemoReference.from_json({
        'asset': 'BTC.BTC',
        'memo': '=:ETH.USDT:0xDest:1000/1/0',
        'reference': '99999',
        'height': '25621817',
        'registration_hash': obs_tx_id,
        'registered_by': 'thor1obs',
        'used_by_txs': [],
    })
    cache, connector, redis = make_cache(response=observed_response)

    block = make_block(make_observed_quorum_tx(obs_tx_id, REFERENCE_MEMO, is_inbound=True))

    await cache.on_data(None, block)

    assert connector.calls == [obs_tx_id]
    assert await cache.get_memo(99999) == observed_response.memo
    assert await cache.get_reference_id_by_registration_hash(obs_tx_id) == 99999


@pytest.mark.asyncio
async def test_on_data_skips_outbound_observed_reference_tx():
    obs_tx_id = 'A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2'
    cache, connector, _redis = make_cache(response=make_reference_payload())

    block = make_block(make_observed_quorum_tx(obs_tx_id, REFERENCE_MEMO, is_inbound=False))

    await cache.on_data(None, block)

    assert connector.calls == []


@pytest.mark.asyncio
async def test_on_data_deduplicates_observed_and_deposit_with_same_id():
    """If native deposit and observed tx carry the same id, only one query should fire."""
    response = make_reference_payload()
    cache, connector, _redis = make_cache(response=response)

    deposit = make_deposit_tx(REFERENCE_TX_HASH, REFERENCE_MEMO)
    observed = make_observed_quorum_tx(REFERENCE_TX_HASH, REFERENCE_MEMO, is_inbound=True)
    block = make_block(deposit, observed)

    await cache.on_data(None, block)

    # Same hash from both sources — only one query expected.
    assert len(connector.calls) == 1
    assert connector.calls[0] == REFERENCE_TX_HASH
