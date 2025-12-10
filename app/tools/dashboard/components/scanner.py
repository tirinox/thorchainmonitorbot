import streamlit as st

from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.scanner_state import ScannerState
from lib.date_utils import format_time_ago, format_date, now_ts, MINUTE
from tools.dashboard.helpers import run_coro


async def block_scanner_info_async(app):
    scanner = BlockScanner(app.deps, role='main')
    return await scanner.state_db.load_state()


def block_scanner_info(app):
    st.subheader('Block scanner')
    data: ScannerState = run_coro(block_scanner_info_async(app))

    status_str = 'SCANNING NOW' if data.is_scanning else 'Idle'
    st.markdown(f"Status: **{status_str}**")

    if len(data.last_message) > 3:
        st.warning(f"Last message: _{data.last_message}_")

    now = now_ts()
    last_scan_ago = now - data.last_scanned_at_ts

    columns = st.columns(2)
    with columns[0]:
        st.subheader(f"Last scanned block")
        st.metric("Last scanned block", f'{data.last_scanned_block:,}', border=True)
        if last_scan_ago > 30:
            st.markdown(f"⚠️ Last scanned block is old!")

    with columns[1]:
        st.subheader(f"Last THOR block")
        st.metric(f"Last THOR block", f'{data.thor_height_block:,}', border=1)
        st.markdown(f"Lag: **{data.lag_behind_thor}** blocks")

    st.markdown(f"Last scanned at: **{format_date(data.last_scanned_at_ts)}** or "
                f"**{format_time_ago(last_scan_ago)}** {('‼️' if last_scan_ago > 5 * MINUTE else '')}")
    st.markdown(f"Scanner started at: **"
                f"{format_date(data.started_at_ts)}** or "
                f"**{format_time_ago(now - data.started_at_ts)}** "
                f"{('‼️' if now - data.started_at_ts > 60 * MINUTE else '')}")
    st.markdown(f"Total blocks scanned: **{data.total_blocks_scanned}**")
    st.markdown(f"Total blocks processed: **{data.total_blocks_processed}**")
    st.markdown(
        f"Max scanning time: **{data.max_block_scanning_time:.2f}** sec, "
        f"avg: **{data.avg_block_scanning_time:.2f}** sec")
    st.markdown(
        f"Max processing time: **{data.max_block_processing_time:.2f}** sec, "
        f"avg: **{data.avg_block_processing_time:.2f}** sec")
    st.markdown(
        f"Errors encountered: **{data.errors_encountered}**, "
        f"success rate: **{data.success_rate:.2f}%**"
    )

    with st.expander("Detailed stats"):
        st.write(data.model_dump())
