import asyncio
from datetime import datetime

import streamlit as st

from tools.dashboard.dedup import dedup_dashboard_info
from tools.dashboard.fetchers import fetchers_dashboard_info
from streamlit_autorefresh import st_autorefresh


async def load_data():
    from lib.db import DB

    db = DB(asyncio.get_running_loop())
    await db.get_redis()

    return {
        'dedup_data': await dedup_dashboard_info(db),
        'fetchers_data': await fetchers_dashboard_info(db),
    }


data = asyncio.run(load_data())

st.set_page_config(layout="wide")
st.title('Bot dashboard')
tab_dedup, tab_other = st.tabs(["TxDedup", "Fetchers"])

# auto refresh page every 10 seconds
st_autorefresh(interval=10000, limit=200, key="page_refresh")

# last refresh time: now
st.write(f"Last refresh: {datetime.now()}")

with tab_dedup:
    st.subheader('TxDeduplication')
    st.table(data['dedup_data'])

with tab_other:
    st.subheader('Fetchers')
    st.table(data['fetchers_data'])
