import asyncio
import json

import streamlit as st

from tools.dashboard.dedup import dedup_dashboard_info


async def load_data():
    from lib.db import DB

    db = DB(asyncio.get_running_loop())
    await db.get_redis()

    return {
        'dedup_data': await dedup_dashboard_info(db),
    }


data = asyncio.run(load_data())

st.set_page_config(layout="wide")
st.title('Bot dashboard')
tab_dedup, tab_other = st.tabs(["TxDedup", "Other"])

with tab_dedup:
    st.subheader('TxDeduplication')
    st.table(data['dedup_data'])

with tab_other:
    st.subheader('Other')
    st.write('Coming soon...')
