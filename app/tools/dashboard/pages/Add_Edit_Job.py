import random
from datetime import datetime
from typing import Optional

import streamlit as st
from pydantic import ValidationError

from models.sched import SchedVariant, SchedJobCfg, CronCfg, DateCfg, IntervalCfg
from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler
from tools.dashboard.helpers import run_coro, get_app


def form_add_job(edit_job: Optional[SchedJobCfg] = None):
    st.subheader("Select job trigger type")
    variants = [SchedVariant.INTERVAL, SchedVariant.CRON, SchedVariant.DATE]
    variant = st.selectbox(
        "Trigger type",
        variants,
        key="variant",
        index=variants.index(edit_job.variant) if edit_job and edit_job.variant else 0
    ) or SchedVariant.INTERVAL

    st.subheader("Base parameters")

    if edit_job:
        func_name = st.text_input("Function (cannot edit)", value=edit_job.func, disabled=True)
    else:
        types = PublicAlertJobExecutor.AVAILABLE_TYPES.keys()
        func_name = st.selectbox("Function", list(types))

    enabled = st.checkbox("Enabled?", value=edit_job.enabled if edit_job else False)

    st.subheader("Trigger parameters")

    interval_cfg = None
    cron_cfg = None
    date_cfg = None

    if variant == SchedVariant.INTERVAL:
        col1, col2, col3 = st.columns(3)
        weeks = col1.number_input("Weeks", 0, 1000,
                                  edit_job.interval.weeks if edit_job and edit_job.interval else 0)
        days = col2.number_input("Days", 0, 1000, edit_job.interval.days if edit_job and edit_job.interval else 0)
        hours = col3.number_input("Hours", 0, 1000,
                                  edit_job.interval.hours if edit_job and edit_job.interval else 1)
        minutes = col1.number_input("Minutes", 0, 1000,
                                    edit_job.interval.minutes if edit_job and edit_job.interval else 0)
        seconds = col2.number_input("Seconds", 0, 1000,
                                    edit_job.interval.seconds if edit_job and edit_job.interval else 0)

        try:
            interval_cfg = IntervalCfg(
                weeks=weeks,
                days=days,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
            )
        except ValidationError as e:
            st.error("Interval configuration is invalid")

    elif variant == SchedVariant.CRON:
        col1, col2, col3 = st.columns(3)
        year = col1.text_input("year", value=edit_job.cron.year if edit_job and edit_job.cron else "")
        month = col2.text_input("month", value=edit_job.cron.month if edit_job and edit_job.cron else "")
        day = col3.text_input("day", value=edit_job.cron.day if edit_job and edit_job.cron else "")
        week = col1.text_input("week", value=edit_job.cron.week if edit_job and edit_job.cron else "")
        day_of_week = col2.text_input("day_of_week",
                                      value=edit_job.cron.day_of_week if edit_job and edit_job.cron else "")
        hour = col3.text_input("hour", value=edit_job.cron.hour if edit_job and edit_job.cron else "")
        minute = col1.text_input("minute",
                                 value=edit_job.cron.minute if edit_job and edit_job.cron else "")
        second = col2.text_input("second",
                                 value=edit_job.cron.second if edit_job and edit_job.cron else "")

        try:
            cron_cfg = CronCfg(
                year=year or None,
                month=month or None,
                day=day or None,
                week=week or None,
                day_of_week=day_of_week or None,
                hour=hour or None,
                minute=minute or None,
                second=second or None,
            )
        except ValidationError as e:
            st.error("Cron configuration is invalid")

    elif variant == SchedVariant.DATE:
        date_val = st.date_input(
            "Run date",
            edit_job.date.run_date.date() if edit_job and edit_job.date else datetime.now().date()
        )
        time_val = st.time_input(
            "Run time",
            edit_job.date.run_date.time() if edit_job and edit_job.date else datetime.now().time()
        )

        run_date = datetime.combine(date_val, time_val)
        try:
            date_cfg = DateCfg(run_date=run_date)
        except ValidationError as e:
            st.error("Date configuration is invalid")

    with st.expander("More Options"):
        max_instances = st.number_input("max_instances", 1, 100, 1)
        coalesce = st.checkbox("coalesce", value=True)
        misfire_grace_time = st.number_input("misfire_grace_time (seconds, optional)", 0, 3600, 0)
        if misfire_grace_time == 0:
            misfire_grace_time = None

    submitted = st.button(
        "Save job" if edit_job else "Create job",
        type='primary', icon='✅',
        use_container_width=True
    )

    if submitted:
        job_id = edit_job.id if edit_job else f"{func_name}_job_{int(datetime.now().timestamp())}"

        try:
            job_cfg = SchedJobCfg(
                id=job_id,
                enabled=enabled,
                func=func_name,
                variant=variant,
                max_instances=max_instances,
                coalesce=coalesce,
                misfire_grace_time=misfire_grace_time,
                interval=interval_cfg,
                cron=cron_cfg,
                date=date_cfg,
            )
            st.success("Job created!" if not edit_job else "Job edited.")
            return job_cfg

        except ValidationError as e:
            st.error("Validation failed")
            st.error(e)
    else:
        return None


any_editing_job = st.session_state.get('editing_job')
if any_editing_job:
    st.markdown(f"### Editing job ID={any_editing_job.id!r}")

job_cfg = form_add_job(any_editing_job)

if job_cfg:
    st.session_state.editing_job = None
    app = get_app()
    sched: PublicScheduler = app.deps.pub_scheduler
    run_coro(sched.add_new_job(job_cfg, load_before=True, allow_replace=(any_editing_job is not None)))
    st.switch_page("pages/ListSchedJobs.py")
