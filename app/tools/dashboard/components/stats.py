import streamlit as st

from lib.depcont import DepContainer
from tools.dashboard.helpers import run_coro


async def stats_dashboard_info_async(app):
    d = app.deps
    users = await d.settings_manager.all_users_having_settings()
    user_settings_count = len(users)
    bot_user_count = await d.settings_manager.bot_user_count()
    return {
        'user_settings_count': user_settings_count,
        'bot_user_count': bot_user_count,
    }


def stats_dashboard_info(app):
    st.subheader('Stats')
    data = run_coro(stats_dashboard_info_async(app))
    st.table(data)
