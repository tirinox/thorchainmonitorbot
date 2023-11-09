import asyncio

from services.jobs.fetch.base import DataController, BaseFetcher
from services.lib.date_utils import format_time_ago, now_ts, MINUTE, seconds_human
from services.lib.depcont import DepContainer
from services.lib.http_ses import ObservableSession, RequestEntry
from services.lib.money import format_percent, short_address
from services.lib.texts import bold, code, pre, ital, link


class AdminMessages:
    TEXT_ROOT_INTRO = "Welcome to the admin's panel!"
    BUTT_CONTROL = 'Control'
    BUTT_INFO = 'Info'
    BUTT_BACK = 'Back'
    TEXT_CONTROL_MENU = 'Control menu'
    TEXT_INFO_MENU = 'Info menu'
    BUTT_HTTP = 'HTTP'
    BUTT_FETCHERS = 'Fetchers'
    BUTT_TASKS = 'Tasks'
    BUTT_GLOBAL_PAUSE = 'Pause all'
    BUTT_GLOBAL_RESUME = 'Resume all'

    def __init__(self, d: DepContainer):
        self.deps = d
        self.creation_timestamp = now_ts()

    @property
    def uptime(self):
        return format_time_ago(now_ts() - self.creation_timestamp)

    async def get_debug_message_text_fetcher(self):
        message = '⚙️' + bold('Debug info') + '\n\n'

        data_ctrl: DataController = self.deps.pool_fetcher.data_controller

        for name, fetcher in data_ctrl.summary.items():
            fetcher: BaseFetcher
            if fetcher.success_rate < 90.0:
                errors = f'❌︎ {fetcher.error_counter} errors'
            else:
                errors = '🆗 No errors' if not fetcher.error_counter else f'🆗︎ {fetcher.error_counter} errors'

            last_ts = fetcher.last_timestamp
            sec_elapsed = now_ts() - last_ts
            last_txt = format_time_ago(sec_elapsed)
            if sec_elapsed > 10 * MINUTE:
                last_txt += '❗'

            interval = seconds_human(fetcher.sleep_period)
            success_rate_txt = format_percent(fetcher.success_rate)

            if fetcher.total_ticks > 0:
                ticks_str = fetcher.total_ticks
            else:
                ticks_str = '🤷 none yet!'

            if fetcher.run_times:
                last_run_time_str = round(fetcher.dbg_last_run_time, 2)
                avg_run_time_str = round(fetcher.dbg_average_run_time, 2)
                run_time_str = (
                    f'\nAvg. run time is {pre(avg_run_time_str)} s, '
                    f'last run time is {pre(last_run_time_str)} s'
                )
            else:
                run_time_str = ''

            message += (
                f"{code(name)}\n"
                f"{errors}. "
                f"Last date: {ital(last_txt)}. "
                f"Interval: {ital(interval)}. "
                f"Success rate: {pre(success_rate_txt)}. "
                f"Total ticks: {ticks_str}{run_time_str}"
                f"\n\n"
            )

        if not data_ctrl.summary:
            message += 'No info'

        message += f'\n<b>Uptime:</b> {self.uptime}'

        return message

    async def get_debug_message_text_session(self, start=0, count=10, with_summary=False):
        message = f'🕸️ {bold("HTTP session info")}\n\n'

        # noinspection PyTypeChecker
        session: ObservableSession = self.deps.session

        now = now_ts()

        top_requests = session.debug_top_calls(start + count + 1)
        for i, item in enumerate(top_requests[start:start + count], start=(start + 1)):
            item: RequestEntry

            med_t = item.avg_time.median or -1
            max_t = item.avg_time.max or -1
            avg_t = item.avg_time.average or -1

            last_ago = format_time_ago(now - item.last_timestamp)
            if item.response_codes:
                code_txt = ' | '.join(f'{bold(k)}: {v}' for k, v in item.response_codes.items())
            else:
                code_txt = 'No response yet'
            caption = short_address(item.url, 40, 80)
            message += (
                f'{i}. {link(item.url, caption)}\n'
                f'{bold(item.total_calls)} calls | {bold(item.total_errors)} err | {last_ago}\n'
                f'Med <b>{med_t:.1f}</b>, avg <b>{avg_t:.1f}</b>, max <b>{max_t:.1f}</b>\n'
                f'Codes: {code_txt}'
            )
            if item.none_count:
                message += f' | None: {item.none_count}'
            if item.text_answer_count:
                message += f' | Non-json: {item.text_answer_count}, last: {pre(item.last_text_answer)}'

            message += '\n\n'

        if with_summary:
            message += (
                f'<b>RPS:</b> {session.rps:.2f} req/sec, '
                f'{ital(session.total_calls)} total requests, '
                f'{ital(session.total_errors)} errors, '
                f'{ital(format_percent(session.success_rate_vs_code, 1))} of 200 code'
            )

        return message

    @staticmethod
    def text_bot_restarted():
        return '🤖 Bot restarted!'

    @staticmethod
    async def get_debug_message_tasks():
        tasks = asyncio.all_tasks()
        message = ''
        for i, task in enumerate(tasks, start=1):
            message += f'{i}. {task}\n\n'
        print(message)
        return f'Check the terminal please.'
