import json
from typing import cast
from types import SimpleNamespace

import pytest

from api.aionode.types import ThorMimirVote
from jobs.vote_recorder import VoteRecorder
from lib.config import Config
from lib.db import DB
from lib.depcont import DepContainer
from lib.date_utils import DAY, now_ts
from models.mimir import MimirHolder, MimirVoteManager, MimirEntry
from tests.fakes import FakeDB


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


@pytest.mark.asyncio
async def test_vote_recorder_constructs_alert_for_key():
    recorder = make_recorder()
    ts = now_ts() - 60
    active_signers = ['node-a', 'node-b', 'node-c']

    holder = make_holder(
        ts,
        [
            ThorMimirVote(key='ALERT_MIMIR', value=1, singer='node-a'),
            ThorMimirVote(key='ALERT_MIMIR', value=1, singer='node-b'),
        ],
        active_signers,
    )

    await recorder.on_data(sender=None, data=holder)

    triggered_option = holder.voting_manager.find_voting('ALERT_MIMIR').options[1]
    alert = await recorder.get_alert_for_key(
        'ALERT_MIMIR',
        DAY,
        holder=holder,
        triggered_option=triggered_option,
    )

    assert alert is not None
    assert alert.holder is holder
    assert alert.voting.key == 'ALERT_MIMIR'
    assert alert.triggered_option is triggered_option
    assert alert.voting_history
    assert max(alert.voting_history) in alert.voting_history
    assert alert.voting.first_seen_ts == ts
    assert alert.voting.last_seen_ts == ts


@pytest.mark.asyncio
async def test_alert_mimir_voting_serializes_current_constant_value():
    recorder = make_recorder()
    ts = now_ts() - 60
    holder = make_holder(
        ts,
        [
            ThorMimirVote(key='CURRENT_MIMIR', value=5, singer='node-a'),
            ThorMimirVote(key='CURRENT_MIMIR', value=5, singer='node-b'),
        ],
        ['node-a', 'node-b', 'node-c'],
    )
    holder._const_map['CURRENT_MIMIR'] = MimirEntry(
        name='CURRENT_MIMIR',
        pretty_name='Current Mimir',
        real_value='7',
        hard_coded_value='1',
        changed_ts=int(ts),
        units='',
        source=MimirEntry.SOURCE_ADMIN,
    )

    await recorder.on_data(sender=None, data=holder)
    alert = await recorder.get_alert_for_key('CURRENT_MIMIR', DAY, holder=holder)

    class FakeLoc:
        @staticmethod
        def format_mimir_value(key, value, units=None):
            return f'{key}:{value}'

    assert alert is not None
    assert alert.current_constant_value == '7'
    assert alert.current_value == '7'
    assert alert.to_dict(FakeLoc())['current_value'] == '7'


