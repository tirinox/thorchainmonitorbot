import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from lib.date_utils import seconds_human
from lib.money import format_percent
from models.sched import SchedJobCfg
from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler, JobStatsModel
from tools.dashboard.helpers import get_app, run_coro, st_running_sign

st.set_page_config(page_title="Scheduled Jobs", layout="wide")

st.title("Configured Jobs")

st_autorefresh(interval=2000, limit=2000, key="page_refresh")

app = get_app()
sched: PublicScheduler = app.deps.pub_scheduler
jobs: list[SchedJobCfg] = run_coro(sched.load_config_from_db(silent=True))

distribution = sched.job_distribution(jobs)
absent_jobs = PublicAlertJobExecutor.get_function_that_are_absent(list(distribution.keys()))

options, selected = [], []
for k, v in distribution.items():
    name = f"{k} ({v})"
    options.append(name)
    selected.append(name)
for func in absent_jobs:
    name = f"{func} (0)"
    options.append(name)

# st.pills, disabled, selected are those who in the distribution
st.pills("Job Functions Distribution",
         options=options,
         # disabled=True,
         selection_mode='multi',
         default=selected)


def call_add_job():
    st.session_state.editing_job = None
    st.switch_page("pages/Add_Edit_Job.py")


if st.button("➕ Add New Job", use_container_width=True, key='add_1'):
    call_add_job()
st.divider()

# Header row
col_config = [4, 2, 1, 4, 3]

header_cols = st.columns(col_config)
with header_cols[0]:
    st.markdown("**ID/Func**")
with header_cols[1]:
    st.markdown("**Variant**")
with header_cols[2]:
    st.markdown("**Enabled**")
with header_cols[3]:
    st.markdown("**Stats**")
with header_cols[4]:
    st.markdown("**Actions**")


@st.dialog('Confirm Delete Job')
def confirm_delete(ident_to_delete):
    st.markdown(f"Are you sure you want to delete job '{ident_to_delete}'?")
    if st.button("Yes, delete it", type="primary"):
        st.session_state.delete_job_id = ident_to_delete
        st.rerun()


if delete_job_id := st.session_state.get('delete_job_id'):
    run_coro(sched.delete_job(delete_job_id))
    del st.session_state['delete_job_id']
    st.rerun()

all_kinds_of_jobs_enabled = [job.func for job in jobs if job.enabled]

# Data rows
for job in jobs:
    cols = st.columns(col_config)
    ident = job.id
    stats: JobStatsModel = run_coro(sched.get_job_stats(ident))
    st.divider()
    with cols[0]:
        st.metric(f'ID={job.id!r}', job.func)
    with cols[1]:
        st.markdown(f"#### {job.variant}")
        if job.variant == 'interval':
            st.markdown(f"⏱ {job.interval.human_readable}")
        elif job.variant == 'cron':
            st.markdown(f"📅 {job.cron.human_readable}")
        elif job.variant == 'date':
            st.markdown(f"📆 {job.date.human_readable}")
    with cols[2]:
        st.markdown("#### ✅ ON" if job.enabled else '#### 🔻OFF')
        if stats.is_running:
            st_running_sign()
        else:
            st.text('🧘IDLE')

    with cols[3]:
        s = {}
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

        st.json(s)

    with cols[4]:
        b_cols = st.columns(2)
        success = ''

        with b_cols[0]:
            if st.button("▶️ Run", key=f"run_{ident}", type="secondary"):
                result = run_coro(sched.post_command(sched.COMMAND_RUN_NOW, job_id=ident))
                if result == 'success':
                    st.success(f"Job '{ident}' executed successfully.")
                else:
                    st.error(f"Failed to execute job '{ident}': {result}")

            if st.button("❌ Delete", key=f"delete_{ident}"):
                confirm_delete(ident)
        with b_cols[1]:
            if st.button("✍️ Edit", key=f"edit_{ident}"):
                st.session_state.editing_job = job
                st.switch_page("pages/Add_Edit_Job.py")
            if st.button("🔻 Disable" if job.enabled else "🆙 Enable", key=f"toggle_{ident}"):
                run_coro(sched.toggle_job_enabled(job.id, not job.enabled))
                st.rerun()

            if st.button("📜Logs...", key=f'view_logs_{ident}'):
                st.session_state['job_id_view_logs'] = ident
                st.switch_page(f"pages/Sched_Logs.py")

if not jobs:
    st.info("No jobs configured yet. Consider adding one below.")

is_dirty = run_coro(sched.any_job_is_dirty())
if is_dirty:
    # if 'apply_clicked' not in st.session_state:
    st.warning("Scheduler configuration has unsaved changes. Please apply the configuration.")
    if applied := st.button("Apply", type="primary", use_container_width=True):
        run_coro(sched.post_command(sched.COMMAND_RELOAD))
        time.sleep(0.5)
        # st.session_state['apply_clicked'] = True
        st.rerun()

if st.button("➕ Add New Job", use_container_width=True):
    call_add_job()

with st.expander("Raw JSON configs"):
    for j in jobs:
        st.subheader(j.id)
        st.json(j.model_dump())
