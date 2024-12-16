import asyncio
import logging
from datetime import datetime

import aiohttp
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from api.aionode.connector import ThorConnector
from jobs.fetch.pool_price import PoolFetcher
from lib.config import Config
from lib.constants import HTTP_CLIENT_ID
from lib.depcont import DepContainer
from notify.public.block_notify import LastBlockStore
from tools.dashboard.curve import curve_dashboard_info
from tools.dashboard.dedup import dedup_dashboard_info
from tools.dashboard.fetchers import fetchers_dashboard_info
from tools.lib.lp_common import LpAppFramework


async def load_data():

    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        d = app.deps
        await d.pool_fetcher.run_once()

        return {
            'dedup_data': await dedup_dashboard_info(d),
            'fetchers_data': await fetchers_dashboard_info(d),
            'curve_data': await curve_dashboard_info(d),
        }


data = asyncio.run(load_data())

st.set_page_config(layout="wide")
st.title('Bot dashboard')

# auto refresh page every 10 seconds
st_autorefresh(interval=10000, limit=200, key="page_refresh")

# last refresh time: now
st.write(f"Last refresh: {datetime.now()}")

tab_dedup, tab_fetchers, tab_curve = st.tabs(["TxDedup", "Fetchers", "Curve"])

with tab_dedup:
    st.subheader('TxDeduplication')
    st.table(data['dedup_data'])

with tab_fetchers:
    st.subheader('Fetchers')
    st.table(data['fetchers_data'])

with tab_curve:
    st.subheader('Curve')
    st.table(data['curve_data'])
