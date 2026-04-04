from collections import defaultdict
from fnmatch import fnmatch
from types import SimpleNamespace
from typing import cast

import pytest

from jobs.scanner.event_db import EventDatabase, EventDbTxDeduplicator
from lib.db import DB
from models.tx import ThorAction


class FakeRedis:
    def __init__(self):
        self.hashes = defaultdict(dict)
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
        bucket = self.hashes.get(name, {})
        return {
            k: (str(v) if isinstance(v, (int, float)) else v)
            for k, v in bucket.items()
        }

    async def expire(self, name, seconds):
        self.expirations[name] = int(seconds)
        return 1

    async def delete(self, *names):
        for name in names:
            self.hashes.pop(name, None)
            self.expirations.pop(name, None)
        return len(names)

    async def keys(self, pattern):
        return [key for key in self.hashes if fnmatch(key, pattern)]


class FakeDB:
    def __init__(self):
        self.redis = FakeRedis()

    async def get_redis(self):
        return self.redis


@pytest.mark.asyncio
async def test_event_db_can_set_and_check_generic_tx_flags():
    db = cast(DB, cast(object, FakeDB()))
    ev_db = EventDatabase(db)

    assert await ev_db.has_tx_flag('tx-1', 'seen_volume') is False

    await ev_db.set_tx_flag('tx-1', 'seen_volume')

    assert await ev_db.has_tx_flag('tx-1', 'seen_volume') is True
    assert await ev_db.has_tx_flag('tx-1', 'seen_large_tx') is False


@pytest.mark.asyncio
async def test_event_db_component_helpers_prefix_seen_and_coexist_with_status_fields():
    db = cast(DB, cast(object, FakeDB()))
    ev_db = EventDatabase(db)

    await ev_db.write_tx_status_kw(
        'tx-2',
        id='tx-2',
        status='observed_in',
        memo='SWAP:BTC.BTC:thor1dest',
        from_address='thor1from',
        in_amount=123,
        in_asset='BTC.BTC',
        out_asset='ETH.ETH',
        block_height=100,
    )
    await ev_db.mark_component_as_seen('tx-2', 'rapid')
    await ev_db.mark_component_as_seen('tx-2', 'seen_large_tx')

    props = await ev_db.read_tx_status('tx-2')

    assert props is not None
    assert props.status == 'observed_in'
    assert await ev_db.is_component_seen('tx-2', 'rapid') is True
    assert await ev_db.is_component_seen('tx-2', 'seen_large_tx') is True
    assert await ev_db.is_component_seen('tx-2', 'volume') is False


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_uses_component_flag():
    db = cast(DB, cast(object, FakeDB()))
    ev_db = EventDatabase(db)
    dedup = EventDbTxDeduplicator(db, 'rapid')

    assert dedup.flag_name == 'seen_rapid'
    assert await dedup.have_ever_seen_hash('tx-3') is False

    await dedup.mark_as_seen('tx-3')

    assert await dedup.have_ever_seen_hash('tx-3') is True
    assert await ev_db.has_tx_flag('tx-3', 'seen_rapid') is True


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_supports_batch_hash_filtering():
    db = cast(DB, cast(object, FakeDB()))
    dedup = EventDbTxDeduplicator(db, 'volume_recorded')

    await dedup.mark_as_seen('tx-seen')

    assert await dedup.only_new_hashes(['tx-new', 'tx-seen']) == ['tx-new']
    assert await dedup.only_seen_hashes(['tx-new', 'tx-seen']) == ['tx-seen']


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_supports_tx_batch_helpers():
    db = cast(DB, cast(object, FakeDB()))
    dedup = EventDbTxDeduplicator(db, 'large_tx_announced')

    tx_new = SimpleNamespace(tx_hash='tx-new')
    tx_seen = SimpleNamespace(tx_hash='tx-seen')
    txs = cast(list[ThorAction], cast(object, [tx_new, tx_seen]))

    await dedup.mark_as_seen_txs(cast(list[ThorAction], cast(object, [tx_seen])))

    only_new = await dedup.only_new_txs(txs)
    only_seen = await dedup.only_seen_txs(txs)

    assert [tx.tx_hash for tx in only_new] == ['tx-new']
    assert [tx.tx_hash for tx in only_seen] == ['tx-seen']


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_have_ever_seen_treats_missing_tx_or_hash_as_seen():
    db = cast(DB, cast(object, FakeDB()))
    dedup = EventDbTxDeduplicator(db, 'wasm_recorder')

    empty_tx = cast(ThorAction, cast(object, SimpleNamespace(tx_hash='')))
    unseen_tx = cast(ThorAction, cast(object, SimpleNamespace(tx_hash='tx-4')))

    assert await dedup.have_ever_seen(cast(ThorAction, cast(object, None))) is True
    assert await dedup.have_ever_seen(empty_tx) is True
    assert await dedup.have_ever_seen(unseen_tx) is False

    await dedup.mark_as_seen('tx-4')

    assert await dedup.have_ever_seen(unseen_tx) is True


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_mark_as_seen_txs_ignores_empty_entries():
    db = cast(DB, cast(object, FakeDB()))
    dedup = EventDbTxDeduplicator(db, 'limit_closed')

    tx_seen = cast(ThorAction, cast(object, SimpleNamespace(tx_hash='tx-seen')))
    tx_empty = cast(ThorAction, cast(object, SimpleNamespace(tx_hash='')))
    txs = cast(list[ThorAction], cast(object, [None, tx_empty, tx_seen]))

    await dedup.mark_as_seen_txs(txs)

    assert await dedup.have_ever_seen_hash('tx-seen') is True
    assert await dedup.have_ever_seen_hash('tx-other') is False


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_only_new_hashes_preserves_order_and_duplicates():
    db = cast(DB, cast(object, FakeDB()))
    dedup = EventDbTxDeduplicator(db, 'volume_recorded')

    await dedup.mark_as_seen('tx-seen')

    tx_hashes = ['tx-b', 'tx-seen', 'tx-a', 'tx-b']

    assert await dedup.only_new_hashes(tx_hashes) == ['tx-b', 'tx-a', 'tx-b']
    assert await dedup.only_seen_hashes(tx_hashes) == ['tx-seen']


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_can_ignore_all_checks_for_hashes():
    db = cast(DB, cast(object, FakeDB()))
    ev_db = EventDatabase(db)
    dedup = EventDbTxDeduplicator(db, 'volume_recorded', ignore_all_checks=True)

    await dedup.mark_as_seen('tx-seen')

    assert await dedup.have_ever_seen_hash('tx-seen') is False
    assert await dedup.only_new_hashes(['tx-new', 'tx-seen']) == ['tx-new', 'tx-seen']
    assert await dedup.only_seen_hashes(['tx-new', 'tx-seen']) == []
    assert await ev_db.has_tx_flag('tx-seen', 'seen_volume_recorded') is False


@pytest.mark.asyncio
async def test_event_db_tx_deduplicator_can_ignore_all_checks_for_tx_objects():
    db = cast(DB, cast(object, FakeDB()))
    dedup = EventDbTxDeduplicator(db, 'large_tx_announced', ignore_all_checks=True)

    tx_new = cast(ThorAction, cast(object, SimpleNamespace(tx_hash='tx-new')))
    tx_seen = cast(ThorAction, cast(object, SimpleNamespace(tx_hash='tx-seen')))
    tx_empty = cast(ThorAction, cast(object, SimpleNamespace(tx_hash='')))
    txs = [tx_new, tx_seen]

    await dedup.mark_as_seen_txs(cast(list[ThorAction], cast(object, [tx_seen, tx_empty])))

    only_new = await dedup.only_new_txs(cast(list[ThorAction], cast(object, txs)))
    only_seen = await dedup.only_seen_txs(cast(list[ThorAction], cast(object, txs)))

    assert [tx.tx_hash for tx in only_new] == ['tx-new', 'tx-seen']
    assert only_seen == []
    assert await dedup.have_ever_seen(tx_new) is False
    assert await dedup.have_ever_seen(tx_seen) is False
    assert await dedup.have_ever_seen(cast(ThorAction, cast(object, None))) is True
    assert await dedup.have_ever_seen(tx_empty) is True


