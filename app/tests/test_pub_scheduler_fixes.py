import json
import time

import pytest
from pydantic import ValidationError

from dashboard.services.jobs import JobPayload
from dashboard.services.schedule import preview_schedule
from models.sched import IntervalCfg, SchedJobCfg
from notify import pub_scheduler as pub_scheduler_module
from notify.pub_scheduler import PublicScheduler, JobStats
from tests.test_pub_scheduler_args import FakeRedis, make_scheduler

HOUR = 3600


def hourly(job_id='hourly', **kwargs):
    return SchedJobCfg(id=job_id, func='sample_job', variant='interval', interval=IntervalCfg(hours=1), **kwargs)


async def sample_job():
    pass


async def started_scheduler(redis, jobs) -> PublicScheduler:
    scheduler = make_scheduler(redis)
    await scheduler.register_job_type('sample_job', sample_job)
    scheduler._scheduled_jobs = list(jobs)
    scheduler.scheduler.start(paused=True)
    return scheduler


def next_run(scheduler, job_id) -> float:
    return scheduler.scheduler.get_job(job_id).next_run_time.timestamp()


@pytest.mark.asyncio
async def test_retry_delay_grows_by_multiplier(monkeypatch):
    scheduler = make_scheduler(FakeRedis())
    scheduler.retries = 4
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(pub_scheduler_module.asyncio, 'sleep', fake_sleep)

    async def always_fails():
        raise RuntimeError('boom')

    await scheduler.register_job_type('always_fails', always_fails)
    result = await scheduler._registered_jobs['always_fails'](None)

    assert result.startswith('failed')
    assert sleeps == [5, 10, 20]


@pytest.mark.asyncio
async def test_run_now_without_job_or_func_does_not_raise():
    scheduler = make_scheduler(FakeRedis())
    assert await scheduler._on_control_message({'command': PublicScheduler.COMMAND_RUN_NOW}) is None


@pytest.mark.asyncio
async def test_interval_keeps_its_rhythm_across_apply_and_restart():
    redis = FakeRedis()
    scheduler = await started_scheduler(redis, [hourly()])
    try:
        await scheduler.apply_scheduler_configuration()
        first = next_run(scheduler, 'hourly')
        assert abs(first - (time.time() + HOUR)) < 5

        # Apply again later (pretend 20 minutes passed): the next run must not move
        anchor_ts = first - 20 * 60
        await JobStats(scheduler.db, 'hourly').set_interval_anchor(anchor_ts, HOUR)
        await scheduler.apply_scheduler_configuration()
        assert next_run(scheduler, 'hourly') == pytest.approx(anchor_ts)
    finally:
        scheduler.scheduler.shutdown(wait=False)

    # a restart of the bot: a new scheduler over the same Redis
    restarted = await started_scheduler(redis, [hourly()])
    try:
        await restarted.apply_scheduler_configuration()
        assert next_run(restarted, 'hourly') == pytest.approx(anchor_ts)
    finally:
        restarted.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_interval_anchor_in_the_past_steps_forward_by_whole_periods():
    redis = FakeRedis()
    scheduler = await started_scheduler(redis, [hourly()])
    try:
        anchor_ts = time.time() - 5 * HOUR - 600  # the bot was down for hours
        await JobStats(scheduler.db, 'hourly').set_interval_anchor(anchor_ts, HOUR)
        await scheduler.apply_scheduler_configuration()
        assert next_run(scheduler, 'hourly') == pytest.approx(anchor_ts + 6 * HOUR)
    finally:
        scheduler.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_changed_interval_starts_a_new_count():
    redis = FakeRedis()
    every_2h = SchedJobCfg(id='hourly', func='sample_job', variant='interval', interval=IntervalCfg(hours=2))
    scheduler = await started_scheduler(redis, [every_2h])
    try:
        await JobStats(scheduler.db, 'hourly').set_interval_anchor(time.time() - 600, HOUR)
        await scheduler.apply_scheduler_configuration()
        assert abs(next_run(scheduler, 'hourly') - (time.time() + 2 * HOUR)) < 5
        stats = await JobStats(scheduler.db, 'hourly').read_stats()
        assert stats.interval_anchor_period == 2 * HOUR
    finally:
        scheduler.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_one_bad_job_does_not_stop_apply():
    bad = SchedJobCfg.model_construct(**{**hourly('bad').model_dump(), 'interval': IntervalCfg(hours=1),
                                         'misfire_grace_time': 0})
    scheduler = await started_scheduler(FakeRedis(), [bad, hourly('good')])
    try:
        await scheduler.apply_scheduler_configuration()
        assert [j.id for j in scheduler.scheduler.get_jobs()] == ['good']
    finally:
        scheduler.scheduler.shutdown(wait=False)


@pytest.mark.parametrize('kwargs', [
    {'interval': {'hours': -1}},
    {'interval': {'minutes': 5, 'seconds': -300}},
    {'interval': {'hours': 1}, 'misfire_grace_time': 0},
    {'interval': {'hours': 1}, 'misfire_grace_time': -5},
    {'interval': {'hours': 1}, 'max_instances': 0},
])
def test_job_config_rejects_values_apscheduler_cannot_take(kwargs):
    with pytest.raises(ValidationError):
        SchedJobCfg(id='x', func='sample_job', variant='interval', **kwargs)


def test_dashboard_rejects_zero_misfire_and_negative_interval():
    with pytest.raises(ValidationError):
        JobPayload(variant='interval', interval={'hours': 1}, misfire_grace_time=0)
    assert not preview_schedule('interval', {'hours': -1}, None, None, 'UTC')['ok']
    assert not preview_schedule('interval', {'minutes': 5, 'seconds': -300}, None, None, 'UTC')['ok']


@pytest.mark.asyncio
async def test_load_skips_invalid_stored_jobs():
    redis = FakeRedis()
    good = hourly('good').model_dump(mode='json')
    redis.values[PublicScheduler.DB_KEY_CONFIG] = json.dumps([
        {**good, 'id': 'negative', 'interval': {'hours': -1}},
        {**good, 'id': 'zero_grace', 'misfire_grace_time': 0},
        good,
    ])
    scheduler = make_scheduler(redis)
    assert [j.id for j in await scheduler.load_config_from_db(silent=True)] == ['good']
