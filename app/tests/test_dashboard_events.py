import asyncio
import json
import time

import pytest

from dashboard.events import EventHub, format_sse
from dashboard.runs import RunManager, RunStatus, RunConflict
from jobs.scanner.scanner_state import ScannerStateDB, ScannerState
from lib.events import publish_event, EventType, EventThrottle, DASHBOARD_EVENTS_CHANNEL
from lib.log_db import CircularLog
from notify.pub_scheduler import PublicScheduler, JobStats
from tests.fakes import FakeRedis, FakeDB, FakePubSubRedis


class PubRedis(FakePubSubRedis):
    def events(self, event_type=None, channel=DASHBOARD_EVENTS_CHANNEL):
        return super().events(event_type, channel)


class BrokenRedis(FakeRedis):
    async def publish(self, channel, message):
        raise ConnectionError('redis is down')


@pytest.mark.asyncio
async def test_publish_event_payload_and_never_raises():
    redis = PubRedis()
    await publish_event(FakeDB(redis), EventType.FLAGS, path='a:b', value=True)
    [event] = redis.events()
    assert event['type'] == 'flags' and event['path'] == 'a:b' and event['value'] is True
    assert event['ts'] > 0

    await publish_event(FakeDB(BrokenRedis()), EventType.FLAGS)  # swallowed
    await publish_event(FakeDB(lazy=True), EventType.FLAGS)  # no connection yet: no-op


def test_event_throttle():
    throttle = EventThrottle(min_interval=60)
    assert throttle.allow('a')
    assert not throttle.allow('a')
    assert throttle.allow('b')


@pytest.mark.asyncio
async def test_circular_log_publishes_entries():
    redis = PubRedis()
    log = CircularLog('PublicScheduler', FakeDB(redis))
    await log.info('run', phase='start', job='j1')
    [event] = redis.events(EventType.LOG)
    assert event['source'] == 'PublicScheduler'
    assert event['entry']['action'] == 'run' and event['entry']['phase'] == 'start'


@pytest.mark.asyncio
async def test_scanner_state_events_are_throttled():
    redis = PubRedis()
    state_db = ScannerStateDB(FakeDB(redis), role='main')
    for _ in range(5):
        await state_db.save_state(ScannerState(role='main'))
    events = redis.events(EventType.SCANNER)
    assert len(events) == 1 and events[0]['role'] == 'main'


def test_event_hub_fans_out_and_drops_slow_clients():
    hub = EventHub(db=None)
    fast, slow = hub.subscribe(), hub.subscribe()
    slow.queue = asyncio.Queue(maxsize=1)

    hub.dispatch({'type': 'log', 'n': 1})
    hub.dispatch({'type': 'log', 'n': 2})

    assert fast.queue.qsize() == 2
    assert slow.overflowed
    assert hub.subscriber_count == 1

    hub.unsubscribe(fast)
    assert hub.subscriber_count == 0


def test_format_sse():
    assert format_sse({'type': 'x', 'a': 1}) == 'data: {"type": "x", "a": 1}\n\n'


# ---------- runs ----------

class FakeScheduler:
    COMMAND_RUN_NOW = PublicScheduler.COMMAND_RUN_NOW

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []
        self.release = asyncio.Event()

    async def post_command(self, command, timeout=15.0, **kwargs):
        self.calls.append({'command': command, 'timeout': timeout, **kwargs})
        await self.release.wait()
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


async def _run_to_end(outcome, **start_kwargs):
    redis = PubRedis()
    sched = FakeScheduler(outcome)
    manager = RunManager(sched, FakeDB(redis))
    run = manager.start(**start_kwargs)
    await asyncio.sleep(0)
    assert run.status == RunStatus.RUNNING
    sched.release.set()
    await asyncio.gather(*manager._tasks)
    return run, sched, redis, manager


@pytest.mark.asyncio
async def test_run_success_publishes_start_and_finish():
    run, sched, redis, _ = await _run_to_end('success', job_id='job1', timeout=100)
    assert run.status == RunStatus.SUCCESS and run.finished_ts
    assert sched.calls == [{'command': 'run_now', 'timeout': 100, 'run_id': run.run_id, 'job_id': 'job1'}]
    statuses = [e['run']['status'] for e in redis.events(EventType.RUN)]
    assert statuses == ['running', 'success']


@pytest.mark.asyncio
async def test_run_failure_timeout_and_rpc_error():
    run, sched, *_ = await _run_to_end('failed with error: boom', func='f', args={'a': 1})
    assert run.status == RunStatus.FAILED and run.result == 'failed with error: boom'
    assert sched.calls[0]['func'] == 'f' and sched.calls[0]['args'] == {'a': 1}

    run, *_ = await _run_to_end(asyncio.TimeoutError(), job_id='j', timeout=5)
    assert run.status == RunStatus.TIMEOUT

    run, *_ = await _run_to_end(RuntimeError('RPC error: nope'), job_id='j')
    assert run.status == RunStatus.ERROR and 'nope' in run.result


@pytest.mark.asyncio
async def test_same_job_cannot_run_twice_at_once():
    sched = FakeScheduler('success')
    manager = RunManager(sched, FakeDB(PubRedis()))
    manager.start(job_id='job1')
    with pytest.raises(RunConflict):
        manager.start(job_id='job1')
    manager.start(job_id='job2')  # other jobs are fine
    assert len(manager.list()) == 2
    await manager.close()


# ---------- scheduler: run_id reaches the run logs ----------

@pytest.mark.asyncio
async def test_run_now_tags_logs_with_run_id():
    redis = PubRedis()
    sched = PublicScheduler(cfg=None, db=FakeDB(redis), loop=asyncio.get_running_loop())

    async def my_job(**kwargs):
        return None

    await sched.register_job_type('my_job', my_job)
    result = await sched._on_control_message({'command': 'run_now', 'func': 'my_job', 'run_id': 'r42'})
    assert result == 'success'

    entries = [e['entry'] for e in redis.events(EventType.LOG)]
    run_entries = [e for e in entries if e['action'] == 'run']
    assert [e['phase'] for e in run_entries] == ['start', 'complete']
    assert all(e['run_id'] == 'r42' for e in run_entries)


@pytest.mark.asyncio
async def test_run_refreshes_next_run_time():
    redis = PubRedis()
    sched = PublicScheduler(cfg=None, db=FakeDB(redis), loop=asyncio.get_running_loop())
    sched.scheduler.start()
    try:
        async def noop():
            pass

        sched.scheduler.add_job(noop, 'interval', hours=1, id='hourly')
        stats = JobStats(sched.db, key='hourly')
        await sched._refresh_next_run_ts('hourly', stats)
        next_ts = (await stats.read_stats()).next_run_ts
        assert 3500 < next_ts - time.time() <= 3600

        await sched._refresh_next_run_ts('gone', JobStats(sched.db, key='gone'))
        assert (await JobStats(sched.db, key='gone').read_stats()).next_run_ts == 0
    finally:
        sched.scheduler.shutdown(wait=False)
