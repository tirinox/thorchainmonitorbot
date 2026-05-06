import json

import streamlit as st

from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler
from tools.dashboard.helpers import get_app, run_coro

st.set_page_config(page_title="Run job now page", layout="wide")


app = get_app()

@st.dialog('Confirm Run Job Now')
def confirm_run_now(run_request):
    st.markdown(f"Are you sure you want to run job '{run_request['func']}' now?")
    if st.button("Yes, run it", type="primary"):
        st.session_state.run_job_request = run_request
        st.rerun()



st.title("Run Job Now")
types = PublicAlertJobExecutor.AVAILABLE_TYPES.keys()
func_name = st.selectbox("Function", list(types))
args_json = st.text_area(
    "Job arguments (JSON object, optional)",
    value="{}",
    height=180,
    help="These kwargs will be passed only for this immediate run.",
)
timeout = st.number_input("Timeout (seconds)", min_value=5, max_value=3600, value=30, step=5)
confirmation = st.checkbox("Ask for confirmation before running", value=True)
if st.button("Run Job Now", type="primary"):
    try:
        job_args = json.loads(args_json.strip() or "{}")
    except json.JSONDecodeError as e:
        st.error(f"Job arguments JSON is invalid: {e}")
    else:
        if not isinstance(job_args, dict):
            st.error("Job arguments must be a JSON object.")
        else:
            run_request = {
                'func': func_name,
                'args': job_args,
                'timeout': timeout,
            }
            if confirmation:
                confirm_run_now(run_request)
            else:
                st.session_state.run_job_request = run_request
                st.rerun()


if run_request := st.session_state.get('run_job_request'):
    sched: PublicScheduler = app.deps.pub_scheduler

    result = run_coro(sched.post_command(
        sched.COMMAND_RUN_NOW,
        func=run_request['func'],
        args=run_request['args'],
        timeout=run_request['timeout'],
    ))
    if result == 'success':
        st.success(f"Job '{run_request['func']}' executed successfully.")
    else:
        st.error(f"Failed to execute job '{run_request['func']}': {result}")

    del st.session_state['run_job_request']
