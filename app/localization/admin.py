from services.jobs.fetch.base import DataController
from services.lib.date_utils import format_time_ago, now_ts, MINUTE, seconds_human
from services.lib.depcont import DepContainer
from services.lib.money import format_percent
from services.lib.texts import bold, code, pre, ital


class AdminMessages:
    def __init__(self, d: DepContainer):
        self.deps = d

    async def get_debug_message_text(self):
        message = bold('Debug info') + '\n\n'

        data_ctrl: DataController = self.deps.pool_fetcher.data_controller

        for name, fetcher in data_ctrl.summary.items():
            errors = '🆗 No errors' if not fetcher.error_counter else f'❌︎ {fetcher.error_counter} errors'

            last_ts = fetcher.last_timestamp
            sec_elapsed = now_ts() - last_ts
            last_txt = format_time_ago(sec_elapsed)
            if sec_elapsed > 10 * MINUTE:
                last_txt += '❗'

            interval = seconds_human(fetcher.sleep_period)
            success_rate_txt = format_percent(fetcher.success_rate, 100.0)

            message += (
                f"{code(name)}\n"
                f"{errors}. "
                f"Last date: {ital(last_txt)}. "
                f"Interval: {ital(interval)}. "
                f"Success rate: {pre(success_rate_txt)}. "
                f"Total ticks: {pre(fetcher.total_ticks)}"
                f"\n\n"
            )

        if not data_ctrl.summary:
            message += 'No info'

        return message
