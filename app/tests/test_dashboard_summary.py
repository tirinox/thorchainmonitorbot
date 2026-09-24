from types import SimpleNamespace

import pytest

from dashboard.audit import AuditLog, diff_dicts, get_actor, LOCAL_ACTOR
from dashboard.services import flags as flag_service
from dashboard.services.summary import (
    Status, evaluate_scanner, evaluate_fetchers, evaluate_jobs, evaluate_config, evaluate_flags, evaluate_errors,
)
from lib.flagship import Flagship
from tests.fakes import FakeDB, FakePubSubRedis

NOW = 1_000_000.0


# ---------- audit ----------

def test_diff_dicts_flattens_nested_and_compares_lists_whole():
    old = {'a': 1, 'cron': {'hour': None, 'minute': '5'}, 'args': {'channels': ['x']}, 'same': 'y'}
    new = {'a': 2, 'cron': {'hour': '12', 'minute': '5'}, 'args': {}, 'same': 'y', 'added': True}
    assert diff_dicts(old, new) == {
        'a': [1, 2],
        'added': [None, True],
        'args': [None, {}],
        'args.channels': [['x'], None],
        'cron.hour': [None, '12'],
    }
    assert diff_dicts({'x': 1}, {'x': 1}) == {}


def test_get_actor_reads_nginx_header():
    assert get_actor(SimpleNamespace(headers={'x-remote-user': ' alice '})) == 'alice'
    assert get_actor(SimpleNamespace(headers={'x-remote-user': ''})) == LOCAL_ACTOR
    assert get_actor(SimpleNamespace(headers={})) == LOCAL_ACTOR


@pytest.mark.asyncio
async def test_audit_log_list_filters_and_facets():
    audit = AuditLog(FakeDB(FakePubSubRedis()))
    await audit.record('flag.set', 'alice', 'a:b', old=True, new=False)
    await audit.record('job.delete', 'bob', 'job1', func='f')
    await audit.record('flag.set', 'bob', 'c:d', old=False, new=True)

    result = await audit.list()
    assert result['total'] == 3
    assert [e['target'] for e in result['items']] == ['c:d', 'job1', 'a:b']
    assert result['facets'] == {'actors': ['alice', 'bob'], 'actions': ['flag.set', 'job.delete']}
    assert result['items'][1]['level'] == 'warning'

    assert (await audit.list(actor='bob'))['matched'] == 2
    assert (await audit.list(action='job.delete'))['items'][0]['details'] == {'func': 'f'}
    assert (await audit.list(q='A:B'))['matched'] == 1
    assert len((await audit.list(limit=1))['items']) == 1


@pytest.mark.asyncio
async def test_flag_changes_are_audited_with_old_value():
    db = FakeDB(FakePubSubRedis())
    ctx = SimpleNamespace(deps=SimpleNamespace(flagship=Flagship(db), db=db), audit=AuditLog(db))

    await flag_service.set_flag(ctx, 'x:y', False, actor='alice')
    await flag_service.set_flag(ctx, 'x:y', False, actor='alice')  # no change: not audited
    await flag_service.set_flag(ctx, 'x:y', True, actor='bob')
    await flag_service.delete_flag(ctx, 'x:y', actor='bob')

    items = (await ctx.audit.list())['items']
    assert [(e['action'], e['actor'], e['details']) for e in items] == [
        ('flag.delete', 'bob', {'old': True}),
        ('flag.set', 'bob', {'old': False, 'new': True}),
        ('flag.set', 'alice', {'old': None, 'new': False}),
    ]


# ---------- summary checks ----------

def scanner_state(since, lag):
    return {'last_scanned_at_ts': NOW - since, 'lag_behind_thor': lag, 'last_scanned_block': 123}


def test_evaluate_scanner():
    assert evaluate_scanner(None, NOW)['status'] == Status.UNKNOWN
    assert evaluate_scanner({'last_scanned_at_ts': 0}, NOW)['status'] == Status.UNKNOWN
    assert evaluate_scanner(scanner_state(5, 1), NOW)['status'] == Status.OK
    assert evaluate_scanner(scanner_state(60, 1), NOW)['status'] == Status.WARN
    assert evaluate_scanner(scanner_state(5, 10), NOW)['status'] == Status.WARN
    assert evaluate_scanner(scanner_state(600, 1), NOW)['status'] == Status.ERROR
    assert evaluate_scanner(scanner_state(0, 1), NOW)['detail'] == 'Block 123 scanned just now'
    assert evaluate_scanner(scanner_state(0, 1), NOW)['value'] == 'lag 1 block'
    check = evaluate_scanner(scanner_state(5, 100), NOW)
    assert check['status'] == Status.ERROR and check['value'] == 'lag 100 blocks'


def tracker(name, ago, period=60, ticks=10, rate=100.0):
    return {'name': name, 'last_timestamp': NOW - ago, 'sleep_period': period, 'total_ticks': ticks,
            'success_rate': rate}


def test_evaluate_fetchers():
    assert evaluate_fetchers(None, NOW)['status'] == Status.UNKNOWN
    assert evaluate_fetchers({'trackers': []}, NOW)['status'] == Status.UNKNOWN

    ok = evaluate_fetchers({'trackers': [tracker('a', 30), tracker('never', 10 ** 6, ticks=0)]}, NOW)
    assert ok['status'] == Status.OK and ok['value'] == '1/1 fresh'

    # a 30-minute fetcher that ran 40 minutes ago is fine; a 1-minute one silent for 15 minutes is stale
    slow_ok = evaluate_fetchers({'trackers': [tracker('slow', 40 * 60, period=30 * 60)]}, NOW)
    assert slow_ok['status'] == Status.OK
    stale = evaluate_fetchers({'trackers': [tracker('fast', 15 * 60), tracker('b', 10)]}, NOW)
    assert stale['status'] == Status.ERROR and stale['items'][0]['label'] == 'fast'

    flaky = evaluate_fetchers({'trackers': [tracker('a', 10, rate=50.0)]}, NOW)
    assert flaky['status'] == Status.WARN and 'success rate 50%' in flaky['items'][0]['text']

    paused = evaluate_fetchers({'all_paused': True, 'trackers': [tracker('a', 10)]}, NOW)
    assert paused['status'] == Status.WARN


def job(job_id, enabled=True, last_status='ok', next_in=600, last_error=None):
    return {
        'config': {'id': job_id, 'enabled': enabled},
        'stats': {'last_status': last_status, 'next_run_ts': NOW + next_in if next_in is not None else None,
                  'last_error': last_error},
    }


def test_evaluate_jobs_and_config():
    assert evaluate_jobs({'jobs': []}, NOW)['status'] == Status.WARN

    ok = evaluate_jobs({'jobs': [job('a'), job('off', enabled=False, last_status='error')]}, NOW)
    assert ok['status'] == Status.OK and ok['value'] == '1/2 enabled'

    failing = evaluate_jobs({'jobs': [job('a', last_status='error', last_error='boom')]}, NOW)
    assert failing['status'] == Status.ERROR and failing['items'] == [{'label': 'a', 'text': 'boom'}]

    overdue = evaluate_jobs({'jobs': [job('a', next_in=-3600), job('b', next_in=-60)]}, NOW)
    assert overdue['status'] == Status.WARN and [i['label'] for i in overdue['items']] == ['a']

    assert evaluate_config({'is_dirty': True})['status'] == Status.WARN
    assert evaluate_config({'is_dirty': False})['status'] == Status.OK
    assert evaluate_config(None)['status'] == Status.UNKNOWN


def test_evaluate_flags_and_errors():
    assert evaluate_flags([{'path': 'a', 'value': True}])['status'] == Status.OK
    off = evaluate_flags([{'path': 'a', 'value': True}, {'path': 'b', 'value': False}])
    assert off['status'] == Status.WARN and off['value'] == '1 off' and off['items'][0]['label'] == 'b'

    logs = [
        {'_ts': NOW - 60, 'level': 'error', 'action': 'run', 'job_id': 'j1', 'error': 'boom'},
        {'_ts': NOW - 30, 'level': 'info', 'action': 'run'},
        {'_ts': NOW - 2 * 86400, 'level': 'error', 'action': 'run', 'job_id': 'old'},
    ]
    errors = evaluate_errors(logs, NOW)
    assert errors['status'] == Status.WARN and errors['value'] == '1 in 24h'
    assert errors['items'][0]['label'] == 'j1' and errors['items'][0]['text'] == 'boom'
    assert evaluate_errors([], NOW)['status'] == Status.OK


def test_worst_status():
    assert Status.worst([Status.OK, Status.WARN, Status.UNKNOWN]) == Status.WARN
    assert Status.worst([Status.OK, Status.ERROR]) == Status.ERROR
    assert Status.worst([]) == Status.OK
