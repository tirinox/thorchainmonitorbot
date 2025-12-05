import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from lib.date_utils import seconds_human
from lib.money import format_percent
from models.sched import SchedJobCfg
from notify.pub_scheduler import PublicScheduler, JobStatsModel
from tools.dashboard.helpers import get_app, run_coro, st_running_sign

st.set_page_config(page_title="Scheduled Jobs", layout="wide")

st.title("Configured Jobs")

st_autorefresh(interval=2000, limit=2000, key="page_refresh")


def set_message_rerun(_msg):
    st.session_state['success_msg'] = _msg
    st.rerun()


if msg := st.session_state.get('success_msg'):
    st.success(msg)
    del st.session_state['success_msg']

# Header row
col_config = [3, 1, 1, 4, 2]

header_cols = st.columns(col_config)
with header_cols[0]:
    st.markdown("**ID/Func**")
with header_cols[1]:
    st.markdown("**Variant**")
with header_cols[2]:
    st.markdown("**Enabled**")
with header_cols[3]:
    st.markdown("**Params**")
with header_cols[4]:
    st.markdown("**Actions**")

app = get_app()
sched: PublicScheduler = app.deps.pub_scheduler
jobs: list[SchedJobCfg] = run_coro(sched.load_config_from_db(silent=True))


@st.dialog('Confirm Delete Job')
def confirm_delete(ident_to_delete):
    st.markdown(f"Are you sure you want to delete job '{ident_to_delete}'?")
    if st.button("Yes, delete it", type="primary"):
        st.session_state.delete_job_id = ident_to_delete
        st.rerun()


if delete_job_id := st.session_state.get('delete_job_id'):
    run_coro(sched.delete_job(delete_job_id))
    del st.session_state['delete_job_id']
    set_message_rerun(f"Job '{delete_job_id}' deleted.")

# Data rows
for job in jobs:
    cols = st.columns(col_config)
    ident = job.id
    stats: JobStatsModel = run_coro(sched.get_job_stats(ident))

    with cols[0]:
        st.markdown(f"### {job.func}")
        st.code(f'ID={job.id!r}', language='python')
        if stats.is_running:
            st_running_sign()
        else:
            st.text('Idle')
    with cols[1]:
        st.subheader(job.variant)
    with cols[2]:
        st.subheader("✅ YES" if job.enabled else '🔻NO')
    with cols[3]:
        trig = job.model_dump(exclude_none=True,
                              exclude={'id', 'func', 'enabled', 'variant', 'max_instances', 'coalesce'})
        s = trig['stats'] = {}
        if stats.last_status == "error":
            s["error"] = repr(stats.last_error)
        s["count"] = stats.run_count
        s["errors"] = stats.error_count
        s["rate"] = format_percent(stats.run_count - stats.error_count, stats.run_count)
        s["last_elapsed"] = seconds_human(stats.last_elapsed)
        s["avg_elapsed"] = seconds_human(stats.avg_elapsed)
        if stats.last_ts:
            s["last"] = f'{seconds_human(time.time() - stats.last_ts)} ago'
        if stats.next_run_ts:
            next_run_diff = stats.next_run_ts - time.time()
            in_past = next_run_diff < 0
            s["next_run"] = (
                f'passed {seconds_human(-next_run_diff)}' if in_past else f'in {seconds_human(next_run_diff)}')

        st.json(trig)

    with cols[4]:
        b_cols = st.columns(2)
        success = ''

        with b_cols[0]:
            if st.button("▶️", key=f"run_{ident}", type="secondary"):
                run_coro(sched.post_command(sched.COMMAND_RUN_NOW, job_id=ident))
                set_message_rerun(f"Job '{ident}' triggered to run now.")

            if st.button("❌", key=f"delete_{ident}"):
                confirm_delete(ident)
        with b_cols[1]:
            if st.button("✍️", key=f"edit_{ident}"):
                st.session_state.editing_job = job
                st.switch_page("pages/_AddEditJob.py")
            if st.button("Disable" if job.enabled else "Enable", key=f"toggle_{ident}"):
                run_coro(sched.toggle_job_enabled(job.id, not job.enabled))
                set_message_rerun(f"Job is enabled" if job.enabled else "Job is disabled")

            if st.button("Logs...", key=f'view_logs_{ident}'):
                st.session_state['job_id_view_logs'] = ident
                st.switch_page(f"pages/SchedLogs.py")

if not jobs:
    st.info("No jobs configured yet. Consider adding one below.")

is_dirty = run_coro(sched.any_job_is_dirty())
if is_dirty:
    if 'apply_clicked' not in st.session_state:
        st.warning("Scheduler configuration has unsaved changes. Please apply the configuration.")
    if applied := st.button("Apply", type="primary", use_container_width=True):
        run_coro(sched.post_command(sched.COMMAND_RELOAD))
        st.session_state['apply_clicked'] = True
        set_message_rerun("Reload command sent to scheduler!")

if st.button("Add New Job", use_container_width=True):
    st.session_state.editing_job = None
    st.switch_page("pages/_AddEditJob.py")

with st.expander("Raw JSON configs"):
    for j in jobs:
        st.subheader(j.id)
        st.json(j.model_dump())
