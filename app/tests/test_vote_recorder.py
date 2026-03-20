import json
from collections import defaultdict
from typing import cast

import pytest

from api.aionode.types import ThorMimirVote
from jobs.vote_recorder import VoteRecorder
from lib.config import Config
from lib.db import DB
from lib.depcont import DepContainer
from models.mimir import MimirHolder, MimirVoteManager
from types import SimpleNamespace


class FakeRedis:
    def __init__(self):
        self.hashes = defaultdict(dict)

    async def hset(self, name, *args, mapping=None):
        bucket = self.hashes[name]
        if mapping is not None:
            for key, value in mapping.items():
                bucket[key] = value
            return len(mapping)
        if len(args) == 2:
            field, value = args
            bucket[field] = value
            return 1
        raise TypeError("Unsupported hset call")

    async def hget(self, name, field):
        return self.hashes.get(name, {}).get(field)

    async def hgetall(self, name):
        return dict(self.hashes.get(name, {}))

    async def delete(self, *names):
        for name in names:
            self.hashes.pop(name, None)


class FakeDB:
    def __init__(self):
        self.redis = FakeRedis()


def make_recorder() -> VoteRecorder:
    deps = DepContainer()
    fake_db = cast(object, FakeDB())
    fake_cfg = cast(object, SimpleNamespace(network_id='mainnet'))
    deps.db = cast(DB, fake_db)
    deps.cfg = cast(Config, fake_cfg)
    return VoteRecorder(deps)


def make_holder(ts: float, votes: list[ThorMimirVote], active_signers: list[str]) -> MimirHolder:
    holder = MimirHolder()
    holder.voting_manager = MimirVoteManager(votes, active_signers, exclude_keys=[])
    holder.last_timestamp = ts
    holder.last_thor_block = 123
    return holder


@pytest.mark.asyncio
async def test_vote_recorder_updates_last_timestamp_only_for_new_signers():
    recorder = make_recorder()
    active_signers = ['node-a', 'node-b', 'node-c']

    await recorder.on_data(
        sender=None,
        data=make_holder(
            100.0,
            [
                ThorMimirVote(key='TEST_MIMIR', value=1, singer='node-a'),
                ThorMimirVote(key='TEST_MIMIR', value=1, singer='node-b'),
            ],
            active_signers,
        ),
    )
    assert await recorder.get_vote_timestamps('TEST_MIMIR') == (100.0, 100.0)

    await recorder.on_data(
        sender=None,
        data=make_holder(
            200.0,
            [
                ThorMimirVote(key='TEST_MIMIR', value=2, singer='node-a'),
                ThorMimirVote(key='TEST_MIMIR', value=1, singer='node-b'),
            ],
            active_signers,
        ),
    )
    assert await recorder.get_vote_timestamps('TEST_MIMIR') == (100.0, 100.0)

    await recorder.on_data(
        sender=None,
        data=make_holder(
            300.0,
            [
                ThorMimirVote(key='TEST_MIMIR', value=2, singer='node-a'),
                ThorMimirVote(key='TEST_MIMIR', value=1, singer='node-b'),
                ThorMimirVote(key='TEST_MIMIR', value=1, singer='node-c'),
            ],
            active_signers,
        ),
    )
    assert await recorder.get_vote_timestamps('TEST_MIMIR') == (100.0, 300.0)

    raw = await recorder.deps.db.redis.hget(recorder.REDIS_KEY_VOTE_TIMESTAMPS, 'TEST_MIMIR')
    assert json.loads(raw)['signers'] == ['node-a', 'node-b', 'node-c']


@pytest.mark.asyncio
async def test_vote_recorder_migrates_old_timestamp_entries_without_bumping_last_seen():
    recorder = make_recorder()
    await recorder.deps.db.redis.hset(
        recorder.REDIS_KEY_VOTE_TIMESTAMPS,
        'LEGACY_MIMIR',
        json.dumps({'first': 10.0, 'last': 50.0}),
    )

    await recorder.on_data(
        sender=None,
        data=make_holder(
            100.0,
            [
                ThorMimirVote(key='LEGACY_MIMIR', value=1, singer='node-a'),
                ThorMimirVote(key='LEGACY_MIMIR', value=1, singer='node-b'),
            ],
            ['node-a', 'node-b', 'node-c'],
        ),
    )
    assert await recorder.get_vote_timestamps('LEGACY_MIMIR') == (10.0, 50.0)

    raw = await recorder.deps.db.redis.hget(recorder.REDIS_KEY_VOTE_TIMESTAMPS, 'LEGACY_MIMIR')
    assert json.loads(raw)['signers'] == ['node-a', 'node-b']

    await recorder.on_data(
        sender=None,
        data=make_holder(
            200.0,
            [
                ThorMimirVote(key='LEGACY_MIMIR', value=1, singer='node-a'),
                ThorMimirVote(key='LEGACY_MIMIR', value=1, singer='node-b'),
                ThorMimirVote(key='LEGACY_MIMIR', value=2, singer='node-c'),
            ],
            ['node-a', 'node-b', 'node-c'],
        ),
    )
    assert await recorder.get_vote_timestamps('LEGACY_MIMIR') == (10.0, 200.0)

