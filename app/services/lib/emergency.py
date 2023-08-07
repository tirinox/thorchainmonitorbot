import asyncio
from contextlib import suppress
from datetime import datetime
from typing import NamedTuple

from aiogram.types import ParseMode

from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class ReportedEvent(NamedTuple):
    module: str
    message: str
    date: datetime
    kwargs: dict
    being_handled: bool = False


class EmergencyReport(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._q = asyncio.Queue()
        self._running = False
        self._sleep_time = 1.0

        admins = self.deps.cfg.get('telegram.admins')
        assert admins, "there must be admins"

        self._admin_id = admins[0]
        self.logger.info(f'I will send emergency reports to Telegram user #{self._admin_id}!')

    async def run_worker(self):
        if self._running:
            self.logger.error('Already running!')
            return

        self._running = True

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

    async def report(self, module: str, message: str, **kwargs):
        if not self._running:
            raise Exception('First you must run this in background. Use "await run()" method!')

        self._q.put_nowait(ReportedEvent(module, message, datetime.now(), kwargs))

    async def _process_item(self, e: ReportedEvent):
        bot = self.deps.telegram_bot.bot

        text = f"❗<pre>[{e.date}]</pre> at module '<b>{e.module}</b>'\n" \
               f"<code>{e.message}</code>"

        if e.kwargs:
            for i, key in enumerate(sorted(e.kwargs.keys()), start=1):
                text += f'\n<pre>{i: 2}. {key} = {e.kwargs[key]!r} </pre>'

        await bot.send_message(self._admin_id, text=text, parse_mode=ParseMode.HTML)
