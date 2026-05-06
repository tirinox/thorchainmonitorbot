import streamlit as st

from jobs.transfer_recorder import RuneTransferRecorder
from models.transfer import AlertRuneTransferStats
from notify.pub_configure import PublicAlertJobExecutor
from tools.dashboard.helpers import run_coro


async def rune_transfer_stats_dashboard_info_async(app):
    d = app.deps
    recorder = RuneTransferRecorder(d)
    summary = await recorder.get_summary(days=PublicAlertJobExecutor.RUNE_TRANSFER_STATS_SUMMARY_DAYS)
    usd_per_rune = await d.pool_cache.get_usd_per_rune()
    return AlertRuneTransferStats.from_summary(summary, usd_per_rune=usd_per_rune)


def _rune_transfer_stats_table(data: AlertRuneTransferStats):
    return [
        {'metric': 'Period', 'value': f'{data.period_days} days'},
        {'metric': 'Date range', 'value': f'{data.start_date} — {data.end_date}'},
        {'metric': 'Total volume', 'value': data.volume_rune},
        {'metric': 'Transfers', 'value': data.transfer_count},
        {'metric': 'CEX inflow', 'value': data.cex_inflow_rune},
        {'metric': 'CEX outflow', 'value': data.cex_outflow_rune},
        {'metric': 'CEX netflow', 'value': data.cex_netflow_rune},
        {'metric': 'CEX deposits', 'value': data.cex_inflow_count},
        {'metric': 'CEX withdrawals', 'value': data.cex_outflow_count},
    ]


def rune_transfer_stats_dashboard_info(app):
    st.subheader('RUNE Transfer Stats')
    data = run_coro(rune_transfer_stats_dashboard_info_async(app))
    st.table(_rune_transfer_stats_table(data))
