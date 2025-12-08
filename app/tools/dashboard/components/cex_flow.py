import streamlit as st

from lib.date_utils import DAY
from notify.public.cex_flow import CEXFlowRecorder
from tools.dashboard.helpers import run_coro


async def cex_flow_dashboard_info_async(app):
    d = app.deps
    cex_flow_notifier = CEXFlowRecorder(d)
    flow = await cex_flow_notifier.read_within_period(period=DAY)
    return flow


def cex_flow_dashboard_info(app):
    st.subheader('CEX Flow')
    data = run_coro(cex_flow_dashboard_info_async(app))
    st.table(data)
