from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from tools.dashboard.components import *
from tools.dashboard.helpers import get_app, run_coro

st.set_page_config(page_title="Bot Dashboard")

app = get_app()
d = app.deps
st.set_page_config(layout="wide")
st.title('Bot dashboard')

# auto refresh page every 10 seconds
st_autorefresh(interval=30000, limit=200, key="page_refresh")

# last refresh time: now
st.write(f"Last refresh: {datetime.now()}")

tab_dedup, tab_fetchers, tab_curve, tab_stats, tab_cex_flow = st.tabs([
    "TxDedup", "Fetchers", "Curve", "Stats", "CEX Flow"
])

with tab_dedup:
    st.subheader('TxDeduplication')
    data = run_coro(dedup_dashboard_info(d))
    st.table(data)

with tab_fetchers:
    st.subheader('Fetchers')
    data = run_coro(fetchers_dashboard_info(d))
    st.table(data)

with tab_curve:
    st.subheader('Curve')
    data = run_coro(curve_dashboard_info(d))
    st.table(data)

with tab_stats:
    st.subheader('Stats')
    data = run_coro(stats_dashboard_info(d))
    st.table(data)

with tab_cex_flow:
    st.subheader('CEX Flow')
    data = run_coro(cex_flow_dashboard_info(d))
    st.table(data)
