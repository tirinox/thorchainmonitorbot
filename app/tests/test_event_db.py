from collections import defaultdict
from fnmatch import fnmatch
from typing import cast

import pytest

from jobs.scanner.event_db import EventDatabase, EventDbTxDeduplicator
from lib.db import DB


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
    dedup = EventDbTxDeduplicator(ev_db, 'rapid')

    assert dedup.flag_name == 'seen_rapid'
    assert await dedup.have_ever_seen_hash('tx-3') is False

    await dedup.mark_as_seen('tx-3')

    assert await dedup.have_ever_seen_hash('tx-3') is True
    assert await ev_db.has_tx_flag('tx-3', 'seen_rapid') is True

