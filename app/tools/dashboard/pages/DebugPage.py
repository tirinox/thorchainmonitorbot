import streamlit as st

from notify.pub_scheduler import PublicScheduler
from tools.dashboard.helpers import get_app, run_coro

app = get_app()

st.set_page_config(page_title="Debug Page", layout="wide")


async def send_reload_confing_message():
    pub_scheduler = PublicScheduler(app.deps.cfg, app.deps.db)
    if pub_scheduler is not None:
        await pub_scheduler.post_command('reload_config')


# button sends a message to the log
if st.button("PUB"):
    run_coro(send_reload_confing_message())
