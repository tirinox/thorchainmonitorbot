import asyncio
import logging
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from tools.dashboard.cex_flow import cex_flow_dashboard_info
from tools.dashboard.curve import curve_dashboard_info
from tools.dashboard.dedup import dedup_dashboard_info
from tools.dashboard.fetchers import fetchers_dashboard_info
from tools.dashboard.stats import stats_dashboard_info
from tools.lib.lp_common import LpAppFramework


async def load_data():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        d = app.deps

        return {
            'dedup_data': await dedup_dashboard_info(d),
            'fetchers_data': await fetchers_dashboard_info(d),
            'curve_data': await curve_dashboard_info(d),
            'stats_data': await stats_dashboard_info(d),
            'cex_flow_data': await cex_flow_dashboard_info(d)
        }


def dashboard_main():
    data = asyncio.run(load_data())

    st.set_page_config(layout="wide")
    st.title('Bot dashboard')

    # auto refresh page every 10 seconds
    st_autorefresh(interval=10000, limit=200, key="page_refresh")

    # last refresh time: now
    st.write(f"Last refresh: {datetime.now()}")

    tab_dedup, tab_fetchers, tab_curve, tab_stats, tab_cex_flow = st.tabs([
        "TxDedup", "Fetchers", "Curve", "Stats", "CEX Flow"
    ])

    with tab_dedup:
        st.subheader('TxDeduplication')
        st.table(data['dedup_data'])

    with tab_fetchers:
        st.subheader('Fetchers')
        st.table(data['fetchers_data'])

    with tab_curve:
        st.subheader('Curve')
        st.table(data['curve_data'])

    with tab_stats:
        st.subheader('Stats')
        st.table(data['stats_data'])

    with tab_cex_flow:
        st.subheader('CEX Flow')
        st.table(data['cex_flow_data'])
