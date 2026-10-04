import asyncio
import html
import os
import sys
import time
import traceback
from collections import deque
from contextlib import suppress
from datetime import datetime, timezone
from typing import NamedTuple, Optional

from aiogram import Bot
from aiogram.types import ParseMode
from aiogram.utils import exceptions as tg_exceptions

from lib.logs import WithLogger

TG_MAX_LEN = 4096
DEDUP_WINDOW = 10 * 60.0  # the same (module, message) is sent once per window, the rest is only counted
MAX_PER_MINUTE = 10  # hard cap of messages to the admin; the excess is counted and told in the next message
SEND_ATTEMPTS = 3
MAX_VALUE_LEN = 300  # of one detail value
MAX_TRACEBACK_LEN = 1200
MAX_DETAILS_LEN = 2000
CLEAN_SEEN_ABOVE = 500


class ReportedEvent(NamedTuple):
    module: str
    message: str
    date: datetime
    kwargs: dict
    repeats: int = 0  # how many identical reports were suppressed since the last sent one
    throttled: int = 0  # how many reports of any kind were dropped by the rate cap since the last sent one
    caller: str = ''  # file:line of the report() call
    traceback: str = ''  # of the exception being handled at the moment of the report, if any


def _fit(raw: str, limit: int) -> str:
    """Cuts raw text so that its HTML-escaped form fits `limit` (cut before escaping: never splits an entity)."""
    raw = raw[:limit]
    while len(html.escape(raw)) > limit:
        raw = raw[:int(len(raw) * 0.8)]
    return html.escape(raw)


def _short(value, limit=MAX_VALUE_LEN) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + f'… (+{len(text) - limit} chars)'


class EmergencyReport(WithLogger):
    """
    Sends emergency messages to the admin's Telegram.
    Never raises from report(). Without admin or bot it only logs (disabled mode, for tools and tests).
    Spam guard: a repeated (module, message) is sent once per DEDUP_WINDOW with the number of skipped repeats;
    at most MAX_PER_MINUTE messages per minute go out at all.
    """

    def __init__(self, admin_id, bot: Optional[Bot]):
        super().__init__()
        self._q = asyncio.Queue()
        self._running = False
        self._sleep_time = 1.0

        self._admin_id = admin_id
        self._bot = bot
        self.enabled = bool(admin_id and bot)

        self._seen: dict[tuple, list] = {}  # key -> [last sent monotonic time, suppressed repeats]
        self._sent_times = deque()
        self._throttled = 0

        if self.enabled:
            self.logger.info(f'I will send emergency reports to Telegram user #{self._admin_id}!')
        else:
            self.logger.error('Emergency reports are DISABLED: there is no admin or no bot. They will only be logged!')

    def run_in_background(self):
        return asyncio.create_task(self.run())

    async def run(self):
        if self._running:
            self.logger.error('Already running!')
            return

        self._running = True
        try:
            while True:
                try:
                    item: ReportedEvent = await self._q.get()
                    await self._process_item(item)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f'Error: {e!r}!')
                finally:
                    with suppress(ValueError):
                        self._q.task_done()
                await asyncio.sleep(self._sleep_time)
        finally:
            self._running = False

    def report(self, module: str, message: str, /, **kwargs):
        # positional-only: a detail may be called "message" or "module" (block error has a "message")
        try:
            self._report(module, message, kwargs, self._caller())
        except Exception as e:
            self.logger.error(f'Emergency report failed: {e!r}')

    async def flush(self, timeout=20.0):
        """Sends what is queued right now, even if run() has not started. For the last words before dying."""
        with suppress(Exception):
            async def drain():
                while not self._q.empty():
                    await self._process_item(self._q.get_nowait())

            await asyncio.wait_for(drain(), timeout)

    @staticmethod
    def _caller() -> str:
        # frame 0 = _caller, 1 = report, 2 = who called report()
        with suppress(Exception):
            f = sys._getframe(2)
            return f'{os.path.basename(f.f_code.co_filename)}:{f.f_lineno}'
        return ''

    def _report(self, module, message, kwargs, caller):
        self.logger.error(f'The module {module!r} has reported an emergency message "{message}", {kwargs = }')

        if not self.enabled:
            return

        now = time.monotonic()
        key = (module, message)
        seen = self._seen.get(key)
        if seen and now - seen[0] < DEDUP_WINDOW:
            seen[1] += 1
            return

        while self._sent_times and now - self._sent_times[0] > 60.0:
            self._sent_times.popleft()
        if len(self._sent_times) >= MAX_PER_MINUTE:
            self._throttled += 1
            return

        if len(self._seen) > CLEAN_SEEN_ABOVE:
            self._seen = {k: v for k, v in self._seen.items() if now - v[0] < DEDUP_WINDOW}

        tb = ''
        if sys.exc_info()[0] is not None:
            tb = traceback.format_exc(limit=-3)

        self._sent_times.append(now)
        self._seen[key] = [now, 0]
        self._q.put_nowait(ReportedEvent(
            module, message, datetime.now(timezone.utc), kwargs,
            repeats=seen[1] if seen else 0, throttled=self._throttled,
            caller=caller, traceback=tb,
        ))
        self._throttled = 0

    @staticmethod
    def format_event(e: ReportedEvent) -> str:
        lines = [
            f"🚨 <b>{_fit(e.module, 100)}</b>",
            f"<code>{_fit(e.message, 500)}</code>",
            '',
            f"🕒 {e.date:%Y-%m-%d %H:%M:%S} UTC" + (f" · 📍 <code>{html.escape(e.caller)}</code>" if e.caller else ''),
        ]
        if e.repeats:
            lines.append(f"🔁 The same message was repeated {e.repeats} more time(s) "
                         f"since the last report (muted for {DEDUP_WINDOW / 60:.0f} min).")
        if e.throttled:
            lines.append(f"⏳ {e.throttled} other message(s) were dropped by the rate limit "
                         f"({MAX_PER_MINUTE}/min). See the logs.")

        if e.kwargs:
            args = [f'{i:2}. {key} = {_short(e.kwargs[key])}' for i, key in enumerate(sorted(e.kwargs), start=1)]
            lines += ['', '<b>Details:</b>', f"<pre>{_fit(chr(10).join(args), MAX_DETAILS_LEN)}</pre>"]

        if e.traceback:
            lines += ['', '<b>Exception:</b>', f"<pre>{_fit(e.traceback.strip(), MAX_TRACEBACK_LEN)}</pre>"]

        return '\n'.join(lines)

    async def _process_item(self, e: ReportedEvent):
        text = self.format_event(e)
        assert len(text) <= TG_MAX_LEN

        for attempt in range(1, SEND_ATTEMPTS + 1):
            try:
                await self._bot.send_message(self._admin_id, text=text, parse_mode=ParseMode.HTML)
                return
            except (tg_exceptions.BotBlocked, tg_exceptions.ChatNotFound, tg_exceptions.Unauthorized) as err:
                # retrying will not help: the admin has not started the bot or has blocked it
                self.logger.error(f'Cannot deliver an emergency message to #{self._admin_id}: {err!r}')
                return
            except tg_exceptions.RetryAfter as err:
                delay = err.timeout + 1
            except Exception as err:
                self.logger.error(f'Emergency message send error (attempt {attempt}): {err!r}')
                delay = 2.0 * attempt
            if attempt < SEND_ATTEMPTS:
                await asyncio.sleep(delay)
        self.logger.error('Emergency message was not delivered!')
