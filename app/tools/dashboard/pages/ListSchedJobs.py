import time

import streamlit as st

from lib.date_utils import seconds_human
from lib.money import format_percent
from models.sched import SchedJobCfg
from notify.pub_scheduler import PublicScheduler, JobStatsModel
from tools.dashboard.components.form_add_job import form_add_job
from tools.dashboard.helpers import get_app, run_coro

st.set_page_config(page_title="Scheduled Jobs", layout="wide")

st.title("Configured Jobs")


# todo:
#   1. is running now flag
#


def set_message_rerun(msg):
    st.session_state['success_msg'] = msg
    st.rerun()


if msg := st.session_state.get('success_msg'):
    st.success(msg)
    del st.session_state['success_msg']

# Header row
col_config = [3, 1, 4, 2]

header_cols = st.columns(col_config)
with header_cols[0]:
    st.markdown("**ID/Func/Variant**")
with header_cols[1]:
    st.markdown("**Enabled**")
with header_cols[2]:
    st.markdown("**Params**")
with header_cols[3]:
    st.markdown("**Actions**")

app = get_app()
sched: PublicScheduler = app.deps.pub_scheduler
jobs: list[SchedJobCfg] = run_coro(sched.load_config_from_db())


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
    with cols[1]:
        st.subheader("✅ YES" if job.enabled else '🔻NO')
        if st.button("Disable" if job.enabled else "Enable", key=f"toggle_{ident}"):
            run_coro(sched.toggle_job_enabled(job.id, not job.enabled))
            set_message_rerun(f"Job is enabled" if job.enabled else "Job is disabled")
    with cols[2]:
        trig = job.model_dump(exclude_none=True,
                              exclude={'id', 'func', 'enabled', 'variant', 'max_instances', 'coalesce'})
        # if job.variant == "interval":
        #     trig = job.interval.model_dump(exclude_none=True)
        # elif job.variant == "cron":
        #     trig = job.cron.model_dump(exclude_none=True)
        # elif job.variant == "date":
        #     trig = job.date.model_dump(exclude_none=True)
        # else:
        #     trig = {}
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

    with cols[3]:
        b_cols = st.columns(3)
        success = ''

        with b_cols[0]:
            if st.button("❌", key=f"delete_{ident}"):
                confirm_delete(ident)
        with b_cols[1]:
            if st.button("▶️", key=f"run_{ident}", type="secondary"):
                run_coro(sched.post_command(sched.COMMAND_RUN_NOW, job_id=ident))
                set_message_rerun(f"Job '{ident}' triggered to run now.")
        with b_cols[2]:
            if st.button("✍️", key=f"edit_{ident}"):
                # todo
                set_message_rerun(f"Navigate to edit page for job '{ident}'.")
if not jobs:
    st.info("No jobs configured yet. Consider adding one below.")

if applied := st.button("Apply", type="primary"):
    run_coro(sched.post_command(sched.COMMAND_RELOAD))
    st.session_state['success_msg'] = "Reload command sent to scheduler!"
    st.rerun()

is_dirty = run_coro(sched.any_job_is_dirty())
if is_dirty and not applied:
    st.warning("Scheduler configuration has unsaved changes. Please apply the configuration.")

with st.expander("Add New Job"):
    job_cfg = form_add_job()
    if job_cfg:
        run_coro(sched.add_new_job(job_cfg, load_before=True))
        st.rerun()

with st.expander("Raw JSON configs"):
    for j in jobs:
        st.subheader(j.id)
        st.json(j.model_dump())
