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
# Header row

col_config = [2, 2, 1, 1, 4, 2]

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
        enable = st.checkbox("?", value=job.enabled, key=f"enabled_{ident}")
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
        trig["last"] = f'{seconds_human(time.time() - stats.last_ts)} ago'

        # красиво упакуем параметры в одну колонку
        # params = ", ".join(f"{k}={v}" for k, v in trig.items()) if trig else ""
        # st.text(params)
        st.json(trig)

    with cols[5]:
        b_cols = st.columns(3)
        success = ''

        with b_cols[0]:
            if st.button("❌", key=f"delete_{ident}"):
                run_coro(sched.delete_job(ident))
                success = f'Job \'{ident}\' deleted.'
        with b_cols[1]:
            if st.button("▶️", key=f"run_{ident}", type="secondary"):
                run_coro(sched.post_command(sched.COMMAND_RUN_NOW, job_id=ident))
                success = f"Job '{ident}' triggered to run now."
        with b_cols[2]:
            if st.button("✍️", key=f"edit_{ident}"):
                # todo
                success = f"Navigate to edit page for job '{ident}'."
        if success:
            st.success(success)

    if enable != job.enabled:
        # Update enabled state in the job config
        run_coro(sched.toggle_job_enabled(job.id, enable))
        st.success(f"Job '{ident}' enabled state updated to {enable}.")

if applied := st.button("Apply", type="primary"):
    run_coro(sched.post_command(sched.COMMAND_RELOAD))
    st.success("Reload command sent to scheduler!")

if not applied and sched.is_dirty:
    st.warning("Scheduler configuration has unsaved changes. Please apply the configuration.")

# button Add navigates to AddSchedJob page
if st.button("Add New Job"):
    form_add_job()

with st.expander("Raw JSON configs"):
    for j in jobs:
        st.subheader(j.id)
        st.json(j.model_dump())
