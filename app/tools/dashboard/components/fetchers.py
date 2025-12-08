import streamlit as st

from jobs.fetch.base import DataController
from lib.date_utils import seconds_human, now_ts, MINUTE, format_time_ago
from lib.money import format_percent
from tools.dashboard.helpers import run_coro


async def fetchers_dashboard_info_async(app):
    d = app.deps
    dc = DataController()
    data = await dc.load_stats(d.db)
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
            'total_ticks': str(f['total_ticks']) if f['total_ticks'] > 0 else '🤷 none yet!',
            'avg_run_time': round(f['avg_run_time'], 2) if f.get('avg_run_time') else 'N/A',
            'last_run_time': round(f['last_run_time'], 2) if f.get('last_run_time') else 'N/A',
        } for f in data['trackers']
    ]


def fetchers_dashboard_info(app):
    st.subheader('Fetchers')
    data = run_coro(fetchers_dashboard_info_async(app))
    st.table(data)
