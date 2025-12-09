import streamlit as st
from streamlit_autorefresh import st_autorefresh

from lib.date_utils import format_date, now_ts
from tools.dashboard.components.cex_flow import cex_flow_dashboard_info
from tools.dashboard.components.curve import curve_dashboard_info
from tools.dashboard.components.dedup import dedup_dashboard_info
from tools.dashboard.components.fetchers import fetchers_dashboard_info
from tools.dashboard.components.scanner import block_scanner_info
from tools.dashboard.components.stats import stats_dashboard_info
from tools.dashboard.helpers import get_app

st.set_page_config(page_title="Bot Dashboard")

app = get_app()

st.set_page_config(layout="wide")
st.title('Bot dashboard')

# auto refresh page
st_autorefresh(interval=1000, limit=200, key="page_refresh")

# last refresh time: now
st.write(f"Last refresh: {format_date(now_ts())}")

tab_dict = {
    "Tx Dedup": dedup_dashboard_info,
    "Fetchers": fetchers_dashboard_info,
    "Curve": curve_dashboard_info,
    "Stats": stats_dashboard_info,
    "CEX Flow": cex_flow_dashboard_info,
    "Block scanner": block_scanner_info,
}

names = list(tab_dict.keys())
tabs = st.tabs(names)
for name, tab in zip(names, tabs):
    with tab:
        function = tab_dict[name]
        function(app)
