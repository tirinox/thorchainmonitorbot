from datetime import datetime

import streamlit as st
from pydantic import ValidationError

from models.sched import SchedVariant, SchedJobCfg
from notify.pub_configure import AVAILABLE_SCHEDULER_JOBS


def form_add_job():
    st.subheader("Select job trigger type")
    variant = st.selectbox(
        "Trigger type",
        [SchedVariant.INTERVAL, SchedVariant.CRON, SchedVariant.DATE],
        key="variant",
    ) or SchedVariant.INTERVAL

    with st.form("job_form"):
        st.subheader("Base parameters")

        func_name = st.selectbox("Function", list(AVAILABLE_SCHEDULER_JOBS))

        enabled = st.checkbox("Enabled", value=True)

        st.subheader("Trigger parameters")

        interval_cfg = None
        cron_cfg = None
        date_cfg = None

        if variant == SchedVariant.INTERVAL:
            col1, col2, col3 = st.columns(3)
            weeks = col1.number_input("Weeks", 0, 1000, 0)
            days = col2.number_input("Days", 0, 1000, 0)
            hours = col3.number_input("Hours", 0, 1000, 0)
            minutes = col1.number_input("Minutes", 0, 1000, 0)
            seconds = col2.number_input("Seconds", 0, 1000, 0)

            interval_cfg = {
                "weeks": weeks or None,
                "days": days or None,
                "hours": hours or None,
                "minutes": minutes or None,
                "seconds": seconds or None,
            }

        elif variant == SchedVariant.CRON:
            col1, col2, col3 = st.columns(3)
            year = col1.text_input("year")
            month = col2.text_input("month")
            day = col3.text_input("day")
            week = col1.text_input("week")
            day_of_week = col2.text_input("day_of_week")
            hour = col3.text_input("hour")
            minute = col1.text_input("minute")
            second = col2.text_input("second")

            cron_cfg = {
                "year": year or None,
                "month": month or None,
                "day": day or None,
                "week": week or None,
                "day_of_week": day_of_week or None,
                "hour": hour or None,
                "minute": minute or None,
                "second": second or None,
            }

        elif variant == SchedVariant.DATE:
            date_val = st.date_input("Run date", datetime.now().date())
            time_val = st.time_input("Run time", datetime.now().time())

            run_date = datetime.combine(date_val, time_val)
            date_cfg = {"run_date": run_date}

        with st.expander("More Options"):
            max_instances = st.number_input("max_instances", 1, 100, 1)
            coalesce = st.checkbox("coalesce", value=True)
            misfire_grace_time = st.number_input("misfire_grace_time (seconds, optional)", 0, 3600, 0)
            if misfire_grace_time == 0:
                misfire_grace_time = None

        submitted = st.form_submit_button("Create Job", type='primary', icon='✅')

    if submitted:
        job_id = f"{func_name}_job_{int(datetime.now().timestamp())}"
        job_data = {
            "id": job_id,
            "func": func_name,
            "enabled": enabled,
            "variant": variant,
            "max_instances": max_instances,
            "coalesce": coalesce,
            "misfire_grace_time": misfire_grace_time,
        }

        if variant == SchedVariant.INTERVAL:
            job_data["interval"] = interval_cfg

        elif variant == SchedVariant.CRON:
            job_data["cron"] = cron_cfg

        elif variant == SchedVariant.DATE:
            job_data["date"] = date_cfg

        try:
            job_cfg = SchedJobCfg(**job_data)
            st.success("Job created!")
            return job_cfg

        except ValidationError as e:
            st.error("Validation failed")
            st.error(e)
