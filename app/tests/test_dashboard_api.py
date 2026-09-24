import asyncio
import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dashboard.server import CSRFGuardMiddleware, StripPrefixMiddleware, CSRF_HEADER
from dashboard.services import jobs
from dashboard.services.jobs import JobPayload, JobNotFound
from dashboard.services.logs import filter_logs, normalize_level
from notify.channel import ChannelDescriptor
from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler
from dashboard.audit import AuditLog
from tests.fakes import FakeDB, FakePubSubRedis

SOME_FUNC = next(iter(PublicAlertJobExecutor.AVAILABLE_TYPES))


# ---------- logs ----------

def _log(ts, level='info', action='run', job='j1', phase='start', **extra):
    return {'_ts': ts, 'level': level, 'action': action, 'job': job, 'phase': phase, **extra}


def test_normalize_level():
    assert normalize_level(None) == 'info'
    assert normalize_level('ERROR') == 'error'
    assert normalize_level('exception') == 'error'
    assert normalize_level('warning') == 'warning'
    assert normalize_level('debug') == 'info'


def test_filter_logs_filters_facets_and_histogram():
    day = 86400
    raw = [
        _log(3 * day + 10, level='error', job='j2', phase='failed', error='boom'),
        _log(3 * day + 5, job='j1', phase='complete', elapsed=1.5),
        _log(2 * day + 1, level='warning', action='config_reloaded', job=None, phase=None),
    ]

    result = filter_logs(raw)
    assert result['total'] == 3
    assert result['matched'] == 3
    assert result['facets']['jobs'] == ['-', 'j1', 'j2']
    assert result['items'][0]['details'] == {'error': 'boom'}
    assert result['items'][2]['job'] == '-'
    assert {'date': '1970-01-03', 'level': 'warning', 'count': 1} in result['histogram']

    only_errors = filter_logs(raw, level='error')
    assert only_errors['matched'] == 1

    by_text = filter_logs(raw, q='BOOM')
    assert [e['job'] for e in by_text['items']] == ['j2']

    by_job = filter_logs(raw, job='j1', limit=10)
    assert by_job['matched'] == 1
    assert by_job['facets'] == result['facets']  # facets are computed from all logs

    limited = filter_logs(raw, limit=1)
    assert len(limited['items']) == 1
    assert limited['matched'] == 3


# ---------- jobs ----------

@pytest_asyncio.fixture
async def ctx():
    db = FakeDB(FakePubSubRedis())
    sched = PublicScheduler(cfg=None, db=db, loop=asyncio.get_running_loop())
    channels = [ChannelDescriptor('telegram', '@chan', 'eng')]
    return SimpleNamespace(
        scheduler=sched,
        sched_lock=asyncio.Lock(),
        deps=SimpleNamespace(broadcaster=SimpleNamespace(channels=channels), db=db),
        audit=AuditLog(db),
    )


@pytest.mark.asyncio
async def test_create_edit_toggle_delete_job(ctx):
    payload = JobPayload(
        func=SOME_FUNC, enabled=True, variant='interval',
        interval={'hours': 2}, args={'foo': 1, 'channels': ['stale']}, channels=['telegram-@chan'],
    )
    created = await jobs.save_job(ctx, payload, actor='alice')
    assert created.id.startswith(f'{SOME_FUNC}_job_')
    assert created.args == {'foo': 1, 'channels': ['telegram-@chan']}

    listing = await jobs.list_jobs(ctx)
    assert len(listing['jobs']) == 1
    item = listing['jobs'][0]
    assert item['schedule']['text'] == 'Every 2 hours'
    assert listing['scheduler_tz']
    assert item['channels']['resolved'][0]['selector'] == 'telegram-@chan'
    assert listing['is_dirty'] is True
    assert listing['distribution'] == {SOME_FUNC: 1}
    assert SOME_FUNC not in listing['absent_types']

    # edit: function cannot change, channels cleared, switched to cron
    edit = JobPayload(func='whatever', variant='cron', cron={'hour': '12'}, interval={'hours': 1})
    edited = await jobs.save_job(ctx, edit, job_id=created.id, actor='bob')
    assert edited.func == SOME_FUNC
    assert edited.interval is None
    assert edited.args == {}

    await jobs.set_job_enabled(ctx, created.id, True)  # the edit above disabled it
    await jobs.set_job_enabled(ctx, created.id, True)  # no change: no audit entry
    stored = json.loads(await ctx.scheduler.db.redis.get(PublicScheduler.DB_KEY_CONFIG))
    assert stored[0]['enabled'] is True and stored[0]['variant'] == 'cron'

    await jobs.set_job_enabled(ctx, created.id, False, actor='bob')
    await jobs.delete_job(ctx, created.id, actor='alice')
    assert (await jobs.list_jobs(ctx))['jobs'] == []

    audit = (await ctx.audit.list())['items']  # newest first
    assert [(e['action'], e['actor']) for e in audit] == [
        ('job.delete', 'alice'), ('job.disable', 'bob'), ('job.enable', 'local'),
        ('job.update', 'bob'), ('job.create', 'alice'),
    ]
    update = audit[3]
    assert update['target'] == created.id
    changes = update['details']['changes']
    assert changes['variant'] == ['interval', 'cron']
    assert changes['cron.hour'] == [None, '12']
    assert changes['args.channels'] == [['telegram-@chan'], None]
    assert audit[0]['level'] == 'warning'  # destructive

    with pytest.raises(JobNotFound):
        await jobs.delete_job(ctx, created.id)


@pytest.mark.asyncio
async def test_save_job_rejects_unknown_function_and_invalid_config(ctx):
    with pytest.raises(ValueError, match='Unknown job function'):
        await jobs.save_job(ctx, JobPayload(func='nope', variant='cron', cron={'hour': '1'}))

    with pytest.raises(ValidationError):
        # variant=date requires the date block
        await jobs.save_job(ctx, JobPayload(func=SOME_FUNC, variant='date'))

    # APScheduler would reject it, and the bot's Apply would then skip every job after this one
    with pytest.raises(ValueError, match='Invalid schedule'):
        await jobs.save_job(ctx, JobPayload(func=SOME_FUNC, variant='cron', cron={'minute': '*/70'}))
    assert (await jobs.list_jobs(ctx))['jobs'] == []


# ---------- middlewares ----------

def _client():
    async def echo(request):
        return PlainTextResponse(request.url.path)

    app = Starlette(routes=[
        Route('/api/thing', echo, methods=['GET', 'POST']),
        Route('/', echo),
    ])
    app.add_middleware(CSRFGuardMiddleware)
    app.add_middleware(StripPrefixMiddleware, prefix='/dashboard')
    return TestClient(app)


def test_prefix_is_stripped():
    client = _client()
    assert client.get('/dashboard/api/thing').text == '/api/thing'
    assert client.get('/dashboard').text == '/'
    assert client.get('/api/thing').text == '/api/thing'


def test_csrf_header_required_for_mutations():
    client = _client()
    assert client.get('/api/thing').status_code == 200
    assert client.post('/api/thing').status_code == 403
    assert client.post('/dashboard/api/thing').status_code == 403
    assert client.post('/api/thing', headers={CSRF_HEADER: '1'}).status_code == 200


# ---------- run history and restore ----------

def test_run_history_takes_finished_runs_per_job_oldest_first():
    raw = [  # newest first, as CircularLog returns them
        {'action': 'run', 'phase': 'failed', 'job_id': 'a', '_ts': 50, 'error': 'boom'},
        {'action': 'run', 'phase': 'start', 'job': 'f', '_ts': 49},  # starts carry no job_id
        {'action': 'run', 'phase': 'complete', 'job_id': 'a', '_ts': 40, 'elapsed': 1.5, 'run_id': 'r1'},
        {'action': 'run', 'phase': 'complete', 'job_id': 'other', '_ts': 30},
        {'action': 'job_toggle_enabled', 'job_id': 'a', '_ts': 25},
        {'action': 'run', 'phase': 'skipped', 'job_id': 'a', '_ts': 20},
        {'action': 'run', 'phase': 'complete', 'job_id': 'a', '_ts': 10},
    ]
    history = jobs.run_history(raw, ['a', 'b'], limit=3)
    assert history['b'] == []
    assert [(r['ts'], r['status']) for r in history['a']] == [(20, 'skipped'), (40, 'ok'), (50, 'error')]
    assert history['a'][1]['manual'] and history['a'][1]['elapsed'] == 1.5
    assert history['a'][2]['error'] == 'boom'


@pytest.mark.asyncio
async def test_restore_deleted_job_from_audit(ctx):
    created = await jobs.save_job(ctx, JobPayload(func=SOME_FUNC, enabled=True, variant='interval',
                                                  interval={'hours': 3}, args={'x': 1}), actor='alice')
    await jobs.delete_job(ctx, created.id, actor='alice')
    deleted = (await ctx.audit.list(action='job.delete'))['items'][0]

    restored = await jobs.restore_job(ctx, deleted['details']['config'], actor='bob')
    assert restored.model_dump() == created.model_dump()
    listing = await jobs.list_jobs(ctx)
    assert [j['config']['id'] for j in listing['jobs']] == [created.id]
    assert listing['jobs'][0]['history'] == []
    assert (await ctx.audit.list())['items'][0]['action'] == 'job.restore'

    with pytest.raises(jobs.JobConflict):
        await jobs.restore_job(ctx, deleted['details']['config'], actor='bob')

    with pytest.raises(ValueError, match='Unknown job function'):
        await jobs.restore_job(ctx, {**deleted['details']['config'], 'id': 'x', 'func': 'gone'}, actor='bob')
