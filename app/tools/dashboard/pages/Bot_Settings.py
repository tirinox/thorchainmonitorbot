import streamlit as st

from tools.dashboard.helpers import get_app

app = get_app()

st.set_page_config(page_title="Bot Settings", layout="wide")


async def send_reload_confing_message():
    pass


st.header("Bot Settings")
st.warning("Nothing here yet.")
