import asyncio
from unittest.mock import patch

import pytest
from aiogram.utils import exceptions as tg_exceptions

from lib import emergency as em
from lib.emergency import EmergencyReport, TG_MAX_LEN


_real_sleep = asyncio.sleep


class FakeBot:
    def __init__(self, errors=()):
        self.texts = []
        self.errors = list(errors)

    async def send_message(self, _chat_id, text, **_kwargs):
        if self.errors:
            raise self.errors.pop(0)
        self.texts.append(text)


def make(bot=None):
    return EmergencyReport(1, bot or FakeBot())


@pytest.mark.asyncio
async def test_report_before_run_and_detail_named_message():
    r = make()
    r.report('scanner', 'Block scan fail', block_no=1, **{'message': 'boom', 'module': 'x'})
    assert r._q.qsize() == 1
    assert r._q.get_nowait().kwargs['message'] == 'boom'


@pytest.mark.asyncio
async def test_dedup_counts_repeats_and_reports_after_window():
    r = make()
    for _ in range(4):
        r.report('m', 'same', tx='a')
    assert r._q.qsize() == 1

    r._seen[('m', 'same')][0] -= r.limits.dedup_window + 1
    r.report('m', 'same')
    assert r._q.qsize() == 2
    r._q.get_nowait()
    assert r._q.get_nowait().repeats == 3


@pytest.mark.asyncio
async def test_rate_cap_and_throttled_note():
    r = make()
    for i in range(r.limits.max_per_minute + 5):
        r.report('m', f'different {i}')
    assert r._q.qsize() == r.limits.max_per_minute
    assert r._throttled == 5

    r._sent_times.clear()
    r.report('m', 'later')
    for _ in range(r.limits.max_per_minute):
        e = r._q.get_nowait()
    assert r._q.get_nowait().throttled == 5


def test_format_fits_telegram_and_keeps_entities_whole():
    ev = em.ReportedEvent('m' * 3000, "'<&>" * 3000, em.datetime.now(), {'k': "'<&>" * 5000, 'txs': 'a' * 9000},
                          traceback="'<&>" * 5000, caller='x.py:1')
    text = EmergencyReport.format_event(ev)
    assert len(text) <= TG_MAX_LEN


@pytest.mark.asyncio
async def test_exception_context_is_attached():
    r = make()
    try:
        raise ValueError('oops')
    except ValueError:
        r.report('m', 'caught')
    ev = r._q.get_nowait()
    assert 'ValueError: oops' in ev.traceback
    assert ev.caller.startswith('test_emergency.py:')


@pytest.mark.asyncio
async def test_retry_after_then_success_and_blocked_is_not_retried():
    bot = FakeBot([tg_exceptions.RetryAfter(0)])
    r = make(bot)
    with patch('lib.emergency.asyncio.sleep', new=lambda *_: _real_sleep(0)):
        r.report('m', 'x')
        await r._process_item(r._q.get_nowait())
    assert len(bot.texts) == 1

    bot = FakeBot([tg_exceptions.BotBlocked('blocked'), tg_exceptions.RetryAfter(0)])
    r = make(bot)
    r.report('m', 'y')
    await r._process_item(r._q.get_nowait())
    assert bot.texts == [] and len(bot.errors) == 1


@pytest.mark.asyncio
async def test_disabled_mode_only_logs():
    r = EmergencyReport(None, None)
    r.report('m', 'x', a=1)
    assert r._q.qsize() == 0


# ---------- who reports ----------

class Spy:
    limits = em.EmergencyLimits()

    def __init__(self):
        self.calls = []

    def report(self, module, message, /, **kwargs):
        self.calls.append((module, message, kwargs))

    async def flush(self):
        pass


def make_deps(spy):
    from types import SimpleNamespace
    from jobs.fetch.base import DataController
    return SimpleNamespace(data_controller=DataController(), emergency=spy)


@pytest.mark.asyncio
async def test_fetcher_reports_only_a_streak_of_errors_and_success_resets_it():
    from jobs.fetch.base import BaseFetcher
    n = em.EmergencyLimits().fetcher_errors_in_a_row

    class Flaky(BaseFetcher):
        fail = True

        async def fetch(self):
            if self.fail:
                raise RuntimeError('down')
            return None

    spy = Spy()
    f = Flaky(make_deps(spy), sleep_period=1)
    for _ in range(n - 1):
        await f.run_once()
    assert spy.calls == []

    await f.run_once()
    assert len(spy.calls) == 1 and spy.calls[0][0].endswith('Flaky')
    assert spy.calls[0][2]['errors_in_a_row'] == n

    f.fail = False
    await f.run_once()
    assert f.consecutive_errors == 0


@pytest.mark.asyncio
async def test_fetcher_that_died_is_reported():
    from jobs.fetch.base import BaseFetcher

    class Dying(BaseFetcher):
        async def fetch(self):
            return None

        async def _run(self):
            raise RuntimeError('boom')

    spy = Spy()
    await Dying(make_deps(spy), sleep_period=1).run()
    assert 'stopped for good' in spy.calls[0][1]


@pytest.mark.asyncio
async def test_block_stall_watchdog():
    from types import SimpleNamespace
    from jobs.scanner.native_scan import BlockStallWatchdog

    spy = Spy()
    scanner = SimpleNamespace(last_block=100, last_block_ts=0)
    w = BlockStallWatchdog(make_deps(spy), scanner, max_silence=300)

    await w.fetch()
    w._since -= 301  # silence while the block stays the same
    await w.fetch()
    assert len(spy.calls) == 1 and spy.calls[0][2]['block_no'] == 100

    spy.calls.clear()
    scanner.last_block = 101  # it moved
    await w.fetch()
    assert spy.calls == []


@pytest.mark.asyncio
async def test_private_scheduler_reports_failing_handler():
    from lib.scheduler import PrivateScheduler

    spy = Spy()
    s = PrivateScheduler(None, 'x')  # no Redis: the handler fails at once
    s.emergency = spy
    await s._run_handler(('ident', 1.0))
    assert spy.calls and spy.calls[0][0] == 'PrivateScheduler:x'


@pytest.mark.asyncio
async def test_flush_sends_without_worker():
    bot = FakeBot()
    r = make(bot)
    r.report('m', 'last words')
    await r.flush()
    assert len(bot.texts) == 1 and r._q.empty()


@pytest.mark.asyncio
async def test_renderer_reports_after_the_last_attempt_only():
    from types import SimpleNamespace
    from lib.html_renderer import InfographicRendererRPC

    spy = Spy()
    r = InfographicRendererRPC(SimpleNamespace(emergency=spy), url='http://x/render')
    r._count, r._step_timeout = 3, 0

    async def fail(*_):
        raise ConnectionError('refused')

    r._render = fail
    with pytest.raises(ConnectionError):
        await r.render('nodes.jinja2', {})
    assert len(spy.calls) == 1 and spy.calls[0][2]['template'] == 'nodes.jinja2'


@pytest.mark.asyncio
async def test_preloading_reports_a_long_failure_and_caps_the_delay():
    from types import SimpleNamespace
    from main import App

    spy = Spy()
    app = App.__new__(App)
    app.logger = SimpleNamespace(info=lambda *_: None, error=lambda *_: None, exception=lambda *_: None)
    sleeps = []

    async def no_sleep(*_):
        pass

    async def fake_sleep(t):
        sleeps.append(t)
        if len(sleeps) >= 8:
            raise asyncio.CancelledError

    async def broken():
        raise ConnectionError('no db')

    app.deps = SimpleNamespace(emergency=spy, db=SimpleNamespace(test_db_connection=broken))
    app._some_sleep = no_sleep
    app.sleep_step = 3
    with patch('main.asyncio.sleep', new=fake_sleep), pytest.raises(asyncio.CancelledError):
        await app._preloading()

    assert len(spy.calls) == 6  # from the 3rd failure on (deduplication is the emergency's own job)
    assert max(sleeps) == spy.limits.preload_max_retry_delay


def test_limits_come_from_the_config_and_keep_defaults():
    from lib.config import Config

    assert em.EmergencyLimits.from_config(Config(data={})) == em.EmergencyLimits()

    limits = em.EmergencyLimits.from_config(Config(data={'emergency': {
        'dedup_window': '2m', 'max_per_minute': 3, 'block_stall_after': 90, 'preload_failures': '7'}}))
    assert limits.dedup_window == 120 and limits.max_per_minute == 3
    assert limits.block_stall_after == 90 and limits.preload_failures == 7
    assert limits.fetcher_errors_in_a_row == 5  # not set: the default


def _report_via_helper(r):
    r.report('m', 'via helper')


@pytest.mark.asyncio
async def test_caller_is_above_the_report_helpers():
    import sys
    r = make()
    _report_via_helper(r); line = sys._getframe().f_lineno  # noqa: E702 (the same line)
    assert r._q.get_nowait().caller == f'test_emergency.py:{line}'


@pytest.mark.asyncio
async def test_fetcher_report_points_at_run_once_not_at_its_helper():
    import linecache
    from jobs.fetch import base
    from jobs.fetch.base import BaseFetcher

    class Failing(BaseFetcher):
        async def fetch(self):
            raise RuntimeError('down')

    r = make()
    f = Failing(make_deps(r), sleep_period=1)
    for _ in range(r.limits.fetcher_errors_in_a_row):
        await f.run_once()
    file, line = r._q.get_nowait().caller.split(':')
    assert file == 'base.py'
    assert "_report_emergency('Fetcher keeps failing'" in linecache.getline(base.__file__, int(line))


@pytest.mark.parametrize('section', [None, 'oops', []])
def test_limits_survive_an_empty_or_wrong_section(section):
    from lib.config import Config
    assert em.EmergencyLimits.from_config(Config(data={'emergency': section})) == em.EmergencyLimits()


def test_bad_limit_values_keep_the_defaults():
    from lib.config import Config
    limits = em.EmergencyLimits.from_config(Config(data={'emergency': {
        'dedup_window': 'soon', 'max_per_minute': 0, 'fetcher_errors_in_a_row': 'x', 'block_stall_after': '-5m',
        'preload_failures': 2}}))
    assert limits == em.EmergencyLimits()._replace(preload_failures=2)
