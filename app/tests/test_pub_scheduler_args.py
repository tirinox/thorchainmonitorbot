import json
from types import SimpleNamespace
from typing import cast

import pytest

from lib.config import Config
from lib.db import DB
from models.sched import IntervalCfg, SchedJobCfg
from notify.pub_scheduler import PublicScheduler


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis

    async def rpush(self, key, value):
        self.redis.lists.setdefault(key, []).append(value)

    async def ltrim(self, key, start, end):
        items = self.redis.lists.get(key, [])
        length = len(items)
        start = max(length + start, 0) if start < 0 else start
        end = length + end if end < 0 else end
        self.redis.lists[key] = items[start:end + 1]

    async def execute(self):
        return True


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.values = {}
        self.lists = {}

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hincrby(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = int(bucket.get(field, 0)) + amount

    async def hincrbyfloat(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = float(bucket.get(field, 0.0)) + amount

    async def hset(self, key, field=None, value=None, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if mapping is not None:
            bucket.update(mapping)
        elif field is not None:
            bucket[field] = value

    async def delete(self, key):
        self.hashes.pop(key, None)
        self.values.pop(key, None)
        self.lists.pop(key, None)

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value

    def pipeline(self):
        return FakePipeline(self)


def make_scheduler(redis: FakeRedis) -> PublicScheduler:
    return PublicScheduler(
        cfg=cast(Config, cast(object, SimpleNamespace())),
        db=cast(DB, cast(object, SimpleNamespace(redis=redis))),
    )


@pytest.mark.asyncio
async def test_public_scheduler_saves_and_loads_job_args():
    scheduler = make_scheduler(FakeRedis())
    scheduler._scheduled_jobs = [
        SchedJobCfg(
            id='job-with-args',
            func='sample_job',
            enabled=True,
            variant='interval',
            interval=IntervalCfg(minutes=15),
            args={'days': 7, 'filters': {'chain': 'BTC'}},
        )
    ]

    await scheduler.save_config_to_db()
    scheduler._scheduled_jobs = []

    loaded_jobs = await scheduler.load_config_from_db(silent=True)

    assert len(loaded_jobs) == 1
    assert loaded_jobs[0].args == {'days': 7, 'filters': {'chain': 'BTC'}}


@pytest.mark.asyncio
async def test_run_job_now_by_id_merges_saved_args_with_run_now_args():
    scheduler = make_scheduler(FakeRedis())
    captured = {}

    async def sample_job(**kwargs):
        captured.update(kwargs)

    await scheduler.register_job_type('sample_job', sample_job)
    scheduler._scheduled_jobs = [
        SchedJobCfg(
            id='job-with-args',
            func='sample_job',
            enabled=False,
            variant='interval',
            interval=IntervalCfg(minutes=5),
            args={'days': 7, 'limit': 10},
        )
    ]

    result = await scheduler.run_job_now_by_id('job-with-args', args={'limit': 25, 'dry_run': True})

    assert result == 'success'
    assert captured == {'days': 7, 'limit': 25, 'dry_run': True}


@pytest.mark.asyncio
async def test_run_job_by_function_supports_direct_args():
    scheduler = make_scheduler(FakeRedis())
    captured = {}

    async def sample_job(**kwargs):
        captured.update(kwargs)

    await scheduler.register_job_type('sample_job', sample_job)

    result = await scheduler.run_job_by_function('sample_job', args={'foo': 'bar', 'nested': {'x': 1}})

    assert result == 'success'
    assert captured == {'foo': 'bar', 'nested': {'x': 1}}


@pytest.mark.asyncio
async def test_add_new_job_preserves_existing_position_on_replace():
    redis = FakeRedis()
    scheduler = make_scheduler(redis)
    scheduler._scheduled_jobs = [
        SchedJobCfg(
            id='job-a',
            func='sample_job',
            enabled=True,
            variant='interval',
            interval=IntervalCfg(minutes=1),
        ),
        SchedJobCfg(
            id='job-b',
            func='sample_job',
            enabled=True,
            variant='interval',
            interval=IntervalCfg(minutes=2),
            args={'days': 7},
        ),
        SchedJobCfg(
            id='job-c',
            func='sample_job',
            enabled=True,
            variant='interval',
            interval=IntervalCfg(minutes=3),
        ),
    ]

    await scheduler.add_new_job(
        SchedJobCfg(
            id='job-b',
            func='sample_job',
            enabled=False,
            variant='interval',
            interval=IntervalCfg(minutes=10),
            args={'days': 30, 'dry_run': True},
        ),
        allow_replace=True,
    )

    assert [job.id for job in scheduler._scheduled_jobs] == ['job-a', 'job-b', 'job-c']
    assert scheduler._scheduled_jobs[1].enabled is False
    assert scheduler._scheduled_jobs[1].interval.minutes == 10
    assert scheduler._scheduled_jobs[1].args == {'days': 30, 'dry_run': True}

    saved_cfg = json.loads(redis.values[PublicScheduler.DB_KEY_CONFIG])
    assert [job['id'] for job in saved_cfg] == ['job-a', 'job-b', 'job-c']
    assert saved_cfg[1]['enabled'] is False
    assert saved_cfg[1]['args'] == {'days': 30, 'dry_run': True}

