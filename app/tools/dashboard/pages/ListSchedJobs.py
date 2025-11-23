import time

import streamlit as st

from lib.date_utils import seconds_human
from lib.money import format_percent
from models.sched import SchedJobCfg
from notify.pub_scheduler import PublicScheduler, JobStatsModel
from tools.dashboard.components.form_add_job import form_add_job
from tools.dashboard.helpers import get_app, run_coro

st.set_page_config(page_title="Scheduled Jobs", layout="wide")

st.title("Configured Jobs (SchedJobCfg)")

# todo:
#   1. is running now flag
#   2. next run in "1h 30m 5s"


def set_message_rerun(msg):
    st.session_state['success_msg'] = msg
    st.rerun()


if msg := st.session_state.get('success_msg'):
    st.success(msg)
    del st.session_state['success_msg']

# Header row
col_config = [2, 2, 1, 1, 4, 3]

header_cols = st.columns(col_config)
with header_cols[0]:
    st.markdown("**ID**")
with header_cols[1]:
    st.markdown("**Func**")
with header_cols[2]:
    st.markdown("**Enabled**")
with header_cols[3]:
    st.markdown("**Variant**")
with header_cols[4]:
    st.markdown("**Params**")
with header_cols[5]:
    st.markdown("**Action**")

app = get_app()
sched: PublicScheduler = app.deps.pub_scheduler
jobs: list[SchedJobCfg] = run_coro(sched.load_config_from_db())

# Data rows
for job in jobs:
    cols = st.columns(col_config)
    ident = job.id

    with cols[0]:
        st.code(job.id)
    with cols[1]:
        st.text(job.func)
    with cols[2]:
        st.text("✅ YES" if job.enabled else '🔻NO')
    with cols[3]:
        st.text(job.variant)
    with cols[4]:
        if job.variant == "interval":
            trig = job.interval.model_dump(exclude_none=True)
        elif job.variant == "cron":
            trig = job.cron.model_dump(exclude_none=True)
        elif job.variant == "date":
            trig = job.date.model_dump(exclude_none=True)
        else:
            trig = {}

        stats: JobStatsModel = run_coro(sched.get_job_stats(ident))
        if stats.last_status == "error":
            trig["error"] = repr(stats.last_error)
        trig["count"] = stats.run_count
        trig["errors"] = stats.error_count
        trig["rate"] = format_percent(stats.run_count - stats.error_count, stats.run_count)
        trig["last_elapsed"] = seconds_human(stats.last_elapsed)
        trig["avg_elapsed"] = seconds_human(stats.avg_elapsed)
        if stats.last_ts:
            trig["last"] = f'{seconds_human(time.time() - stats.last_ts)} ago'

        st.json(trig)

    with cols[5]:
        b_cols = st.columns(4)
        success = ''

        with b_cols[0]:
            if st.button("❌", key=f"delete_{ident}"):
                run_coro(sched.delete_job(ident))
                set_message_rerun(f'Job \'{ident}\' deleted.')
        with b_cols[1]:
            if st.button("▶️", key=f"run_{ident}", type="secondary"):
                run_coro(sched.post_command(sched.COMMAND_RUN_NOW, job_id=ident))
                set_message_rerun(f"Job '{ident}' triggered to run now.")
        with b_cols[2]:
            if st.button("✍️", key=f"edit_{ident}"):
                # todo
                set_message_rerun(f"Navigate to edit page for job '{ident}'.")
        with b_cols[3]:
            if st.button("OFF" if job.enabled else "ON!", key=f"toggle_{ident}"):
                run_coro(sched.toggle_job_enabled(job.id, not job.enabled))
                set_message_rerun(f"Job is enabled" if job.enabled else "Job is disabled")

if applied := st.button("Apply", type="primary"):
    run_coro(sched.post_command(sched.COMMAND_RELOAD))
    st.session_state['success_msg'] = "Reload command sent to scheduler!"
    st.rerun()

is_dirty = run_coro(sched.any_job_is_dirty())
if is_dirty and not applied:
    st.warning("Scheduler configuration has unsaved changes. Please apply the configuration.")

# button Add navigates to AddSchedJob page
if st.button("Add New Job"):
    st.session_state["new_job_form_active"] = not st.session_state.get("new_job_form_active", False)

if st.session_state.get("new_job_form_active"):
    job_cfg = form_add_job()
    if job_cfg:
        run_coro(sched.add_new_job(job_cfg, load_before=True))
        st.rerun()

with st.expander("Raw JSON configs"):
    for j in jobs:
        st.subheader(j.id)
        st.json(j.model_dump())
