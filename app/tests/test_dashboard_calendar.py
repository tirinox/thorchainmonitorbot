import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio

from dashboard.services.calendar import upcoming_runs, FREQUENT_PER_DAY, interval_seconds
from models.sched import SchedJobCfg, IntervalCfg
from notify.pub_scheduler import PublicScheduler, JobStats
from tests.fakes import FakeDB, FakePubSubRedis

# Wednesday 2026-09-23 10:00 UTC
NOW = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc).timestamp()
HOUR = 3600


@pytest_asyncio.fixture
async def make_ctx():
    async def factory(jobs, stats=None):
        db = FakeDB(FakePubSubRedis())
        await db.redis.set(PublicScheduler.DB_KEY_TIMEZONE, 'Etc/UTC')
        sched = PublicScheduler(cfg=None, db=db, loop=asyncio.get_running_loop())
        sched._scheduled_jobs = list(jobs)
        await sched.save_config_to_db()
        for job_id, fields in (stats or {}).items():
            st = JobStats(db, key=job_id)
            if 'next_run_ts' in fields:
                await st.set_next_time_run(fields['next_run_ts'])
            if fields.get('is_dirty'):
                await st.set_is_dirty(True)
            if 'interval_anchor_ts' in fields:
                await st.set_interval_anchor(fields['interval_anchor_ts'], fields['interval_anchor_period'])
        return SimpleNamespace(scheduler=sched, deps=SimpleNamespace(db=db, broadcaster=SimpleNamespace(test_channels=[])))

    return factory


def cron_job(job_id, enabled=True, **cron):
    return SchedJobCfg(id=job_id, func='key_metrics', variant='cron', cron=cron, enabled=enabled)


def by_id(result):
    return {j['id']: j for j in result['jobs']}


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%a %d %H:%M')


def test_interval_seconds():
    assert interval_seconds(IntervalCfg(days=1, hours=2, minutes=3, seconds=4)) == 86400 + 7200 + 180 + 4
    assert interval_seconds(IntervalCfg(weeks=1)) == 7 * 86400


@pytest.mark.asyncio
async def test_cron_jobs_hourly_is_shown_more_often_is_a_band(make_ctx):
    ctx = await make_ctx([
        cron_job('weekly', day_of_week='mon', hour='9'),
        cron_job('hourly', minute='0'),
        cron_job('often', minute='*/10'),
        cron_job('off', enabled=False, hour='12'),
    ])
    result = await upcoming_runs(ctx, days=7, now=NOW)
    jobs = by_id(result)

    assert result['days'] == 7 and result['scheduler_tz'] == 'UTC'
    assert [utc(t) for t in jobs['weekly']['runs']] == ['Mon 28 09:00']
    assert jobs['weekly']['schedule'] == 'At 09:00, on Mondays'

    assert not jobs['hourly']['frequent'] and len(jobs['hourly']['runs']) == 24 * 7
    assert jobs['often']['frequent'] and jobs['often']['runs'] == [] and jobs['often']['per_day'] == FREQUENT_PER_DAY

    # disabled jobs are still computed (the page can show them for planning), flagged as such
    assert not jobs['off']['enabled'] and len(jobs['off']['runs']) == 7


@pytest.mark.asyncio
async def test_interval_jobs_follow_the_bots_real_schedule(make_ctx):
    every_6h = dict(func='top_pools', variant='interval', interval={'hours': 6})
    ctx = await make_ctx(
        [
            SchedJobCfg(id='applied', **every_6h),
            SchedJobCfg(id='stale', **every_6h),
            SchedJobCfg(id='not_applied', **every_6h),
        ],
        stats={
            'applied': {'next_run_ts': NOW + 2 * HOUR},
            'stale': {'next_run_ts': NOW - 7 * HOUR},  # overdue by 7 h: next is 5 h from now
            'not_applied': {'next_run_ts': NOW + 1 * HOUR, 'is_dirty': True},
        })
    jobs = by_id(await upcoming_runs(ctx, days=1, now=NOW))

    assert jobs['applied']['runs'][:3] == [NOW + 2 * HOUR, NOW + 8 * HOUR, NOW + 14 * HOUR]
    assert not jobs['applied']['approximate']

    assert jobs['stale']['runs'][0] == NOW + 5 * HOUR

    # saved but not applied: the bot will start counting at Apply, so this is only an estimate
    assert jobs['not_applied']['approximate'] and jobs['not_applied']['is_dirty']
    assert abs(jobs['not_applied']['runs'][0] - (NOW + 6 * HOUR)) < 5


@pytest.mark.asyncio
async def test_one_off_and_invalid_jobs(make_ctx):
    soon = datetime.fromtimestamp(NOW + 3 * HOUR, timezone.utc).isoformat()
    later = datetime.fromtimestamp(NOW + 30 * 86400, timezone.utc).isoformat()
    ctx = await make_ctx([
        SchedJobCfg(id='soon', func='price_alert', variant='date', date={'run_date': soon}),
        SchedJobCfg(id='later', func='price_alert', variant='date', date={'run_date': later}),
        cron_job('broken', minute='*/70'),
    ])
    jobs = by_id(await upcoming_runs(ctx, days=7, now=NOW))
    assert jobs['soon']['runs'] == [NOW + 3 * HOUR]
    assert jobs['later']['runs'] == []
    assert jobs['broken']['invalid'] and 'step value (70)' in jobs['broken']['invalid']


@pytest.mark.asyncio
async def test_days_are_clamped(make_ctx):
    ctx = await make_ctx([])
    assert (await upcoming_runs(ctx, days=0, now=NOW))['days'] == 1
    assert (await upcoming_runs(ctx, days=365, now=NOW))['days'] == 31


@pytest.mark.asyncio
async def test_unapplied_interval_job_keeps_its_saved_rhythm(make_ctx):
    ctx = await make_ctx(
        [
            SchedJobCfg(id='same_period', func='top_pools', variant='interval', interval={'hours': 6}),
            SchedJobCfg(id='new_period', func='top_pools', variant='interval', interval={'hours': 3}),
        ],
        stats={
            # edited but not applied yet; Apply keeps the anchor only while the period stays the same
            'same_period': {'is_dirty': True, 'interval_anchor_ts': NOW - 4 * HOUR, 'interval_anchor_period': 6 * HOUR},
            'new_period': {'is_dirty': True, 'interval_anchor_ts': NOW - 4 * HOUR, 'interval_anchor_period': 6 * HOUR},
        })
    jobs = by_id(await upcoming_runs(ctx, days=1, now=NOW))

    assert jobs['same_period']['runs'][:2] == [NOW + 2 * HOUR, NOW + 8 * HOUR]
    assert not jobs['same_period']['approximate']
    assert jobs['new_period']['approximate']
