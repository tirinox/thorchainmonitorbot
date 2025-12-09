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



st.title("Run Job Now")
types = PublicAlertJobExecutor.AVAILABLE_TYPES.keys()
func_name = st.selectbox("Function", list(types))
timeout = st.number_input("Timeout (seconds)", min_value=5, max_value=3600, value=30, step=5)
confirmation = st.checkbox("Ask for confirmation before running", value=True)
if st.button("Run Job Now", type="primary"):
    if confirmation:
        confirm_run_now(func_name)
    else:
        st.session_state.run_job_function = func_name
        st.rerun()


if function := st.session_state.get('run_job_function'):
    sched: PublicScheduler = app.deps.pub_scheduler

    result = run_coro(sched.post_command(sched.COMMAND_RUN_NOW, func=function, timeout=timeout))
    if result == 'success':
        st.success(f"Job '{function}' executed successfully.")
    else:
        st.error(f"Failed to execute job '{function}': {result}")

    del st.session_state['run_job_function']
