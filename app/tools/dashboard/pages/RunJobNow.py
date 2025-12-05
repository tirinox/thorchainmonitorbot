import logging

import streamlit as st

from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler
from tools.dashboard.helpers import get_app, run_coro

st.set_page_config(page_title="Run job now page", layout="wide")


app = get_app()

@st.dialog('Confirm Run Job Now')
def confirm_run_now(_function):
    st.markdown(f"Are you sure you want to run job '{_function}' now?")
    if st.button("Yes, run it", type="primary"):
        st.session_state.run_job_function = _function
        st.rerun()


if function := st.session_state.get('run_job_function'):
    sched: PublicScheduler = app.deps.pub_scheduler

    result = run_coro(sched.post_command(sched.COMMAND_RUN_NOW, func=function))
    if result == 'success':
        st.success(f"Job '{function}' executed successfully.")
    else:
        st.error(f"Failed to execute job '{function}': {result}")

    del st.session_state['run_job_function']


st.title("Run Job Now")
types = PublicAlertJobExecutor.AVAILABLE_TYPES.keys()
func_name = st.selectbox("Function", list(types))
if st.button("Run Job Now", type="primary"):
    confirm_run_now(func_name)
