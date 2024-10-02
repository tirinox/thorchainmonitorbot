from lib.date_utils import seconds_human, now_ts, MINUTE, format_time_ago
from lib.db import DB
from jobs.fetch.base import DataController
from lib.money import format_percent


async def fetchers_dashboard_info(db: DB):
    dc = DataController()
    data = await dc.load_stats(db)
    now = now_ts()
    return [
        {
            'name': f['name'],
            'errors': f'❌︎ {f["error_counter"]} errors' if f['success_rate'] < 90.0 else '🆗 No errors' if not f[
                'error_counter'] else f'🆗︎ {f["error_counter"]} errors',
            'last_date': format_time_ago(now - f['last_timestamp']) + '❗' if now - f[
                'last_timestamp'] > 10 * MINUTE else '',
            'interval': seconds_human(f['sleep_period']),
            'success_rate': format_percent(f['success_rate']),
            'total_ticks': f['total_ticks'] if f['total_ticks'] > 0 else '🤷 none yet!',
            'avg_run_time': round(f['avg_run_time'], 2) if f.get('avg_run_time') else 'N/A',
            'last_run_time': round(f['last_run_time'], 2) if f.get('last_run_time') else 'N/A',
        } for f in data['trackers']
    ]

    # for name, fetcher in data_ctrl.summary.items():
    #     fetcher: BaseFetcher
    #     if fetcher.success_rate < 90.0:
    #         errors = f'❌︎ {fetcher.error_counter} errors'
    #     else:
    #         errors = '🆗 No errors' if not fetcher.error_counter else f'🆗︎ {fetcher.error_counter} errors'
    #
    #     last_ts = fetcher.last_timestamp
    #     sec_elapsed = now_ts() - last_ts
    #     last_txt = format_time_ago(sec_elapsed)
    #     if sec_elapsed > 10 * MINUTE:
    #         last_txt += '❗'
    #
    #     interval = seconds_human(fetcher.sleep_period)
    #     success_rate_txt = format_percent(fetcher.success_rate)
    #
    #     if fetcher.total_ticks > 0:
    #         ticks_str = fetcher.total_ticks
    #     else:
    #         ticks_str = '🤷 none yet!'
    #
    #     if fetcher.run_times:
    #         last_run_time_str = round(fetcher.dbg_last_run_time, 2)
    #         avg_run_time_str = round(fetcher.dbg_average_run_time, 2)
    #         run_time_str = (
    #             f'\nAvg. run time is {pre(avg_run_time_str)} s, '
    #             f'last run time is {pre(last_run_time_str)} s'
    #         )
    #     else:
    #         run_time_str = ''
    #
    #     message += (
    #         f"{bold(name)}\n"
    #         f"{errors}. "
    #         f"Last date: {ital(last_txt)}. "
    #         f"Interval: {ital(interval)}. "
    #         f"Success rate: {pre(success_rate_txt)}. "
    #         f"Total ticks: {ticks_str}{run_time_str}"
    #         f"\n\n"
    #     )

    return []
