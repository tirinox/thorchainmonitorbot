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

    r._seen[('m', 'same')][0] -= em.DEDUP_WINDOW + 1
    r.report('m', 'same')
    assert r._q.qsize() == 2
    r._q.get_nowait()
    assert r._q.get_nowait().repeats == 3


@pytest.mark.asyncio
async def test_rate_cap_and_throttled_note():
    r = make()
    for i in range(em.MAX_PER_MINUTE + 5):
        r.report('m', f'different {i}')
    assert r._q.qsize() == em.MAX_PER_MINUTE
    assert r._throttled == 5

    r._sent_times.clear()
    r.report('m', 'later')
    for _ in range(em.MAX_PER_MINUTE):
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
    from jobs.fetch.base import BaseFetcher, ERRORS_IN_A_ROW_TO_REPORT

    class Flaky(BaseFetcher):
        fail = True

        async def fetch(self):
            if self.fail:
                raise RuntimeError('down')
            return None

    spy = Spy()
    f = Flaky(make_deps(spy), sleep_period=1)
    for _ in range(ERRORS_IN_A_ROW_TO_REPORT - 1):
        await f.run_once()
    assert spy.calls == []

    await f.run_once()
    assert len(spy.calls) == 1 and spy.calls[0][0].endswith('Flaky')
    assert spy.calls[0][2]['errors_in_a_row'] == ERRORS_IN_A_ROW_TO_REPORT

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
