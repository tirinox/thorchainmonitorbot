import streamlit as st

from lib.date_utils import DAY
from jobs.transfer_recorder import RuneTransferRecorder
from tools.dashboard.helpers import run_coro


async def cex_flow_dashboard_info_async(app):
    d = app.deps
    recorder = RuneTransferRecorder(d)
    flow = await recorder.get_cex_flow(period=DAY)
    return flow


def cex_flow_dashboard_info(app):
    st.subheader('CEX Flow')
    data = run_coro(cex_flow_dashboard_info_async(app))
    st.table(data)
