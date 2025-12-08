import json
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from lib.date_utils import seconds_human
from notify.pub_scheduler import PublicScheduler
from tools.dashboard.helpers import get_app, run_coro

st.set_page_config(page_title="Scheduler logs", layout="wide")
st_autorefresh(interval=2000, key="refresh")

app = get_app()


# ===== Data loading ===========================================================
async def fetch_logs():
    sched: PublicScheduler = app.deps.pub_scheduler
    logs = await sched.db_log.get_last_logs(10000)
    return logs


raw_logs = run_coro(fetch_logs())

if not raw_logs:
    st.info("No logs yet.")
    st.stop()

df = pd.DataFrame(raw_logs)


# ===== Normalization helpers ==================================================
def to_json_if_dict(value):
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


# Convert dicts to JSON strings for cleaner display/search
for col in df.columns:
    if df[col].dtype == object:
        df[col] = df[col].apply(to_json_if_dict)

job_query_param = st.session_state.get('job_id_view_logs')
if job_query_param:
    if st.button('Reset job id query'):
        del st.session_state['job_id_view_logs']
        st.rerun()

# Timestamp → Time column
if "_ts" in df.columns:
    now = datetime.now().timestamp()
    df["Time"] = df["_ts"].apply(
        lambda x: f'{datetime.fromtimestamp(x).strftime("%Y/%m/%d | %H:%M:%S")} | {seconds_human(now - x)} ago'
        if pd.notna(x)
        else ""
    )
    df["date"] = pd.to_datetime(df["_ts"], unit="s").dt.date

    df.drop(columns=["_ts"], inplace=True)
else:
    df["Time"] = ""

# Ensure level column exists and is formatted with emoji
if "level" not in df.columns:
    df["level"] = "info"


def format_level(level_value: str) -> str:
    if pd.isna(level_value):
        level_value = "info"
    s = str(level_value).lower()
    if "error" in s or "exception" in s:
        return "🔴 " + s.upper()
    if "warn" in s:
        return "🟡 " + s.upper()
    return "🟢 " + s.upper()


df["level_fmt"] = df["level"].apply(format_level)

# Ensure phase exists
if "phase" not in df.columns:
    df["phase"] = "-"

if "job" not in df.columns:
    df["job"] = "-"

if "action" not in df.columns:
    df["action"] = "-"

# ===== Filters (use raw columns, not the final 4-column view) ================
action_list = ["(all)"]
if "action" in df.columns:
    action_list += sorted(df["action"].dropna().unique().tolist())

phase_list = ["(all)"] + sorted(df["phase"].dropna().unique().tolist())
job_types_list = ["(all)"] + sorted(df["job"].dropna().unique().tolist())

col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
with col1:
    f_action = st.selectbox("action", action_list)
with col2:
    f_phase = st.selectbox("phase", phase_list)
with col3:
    f_job = st.selectbox("job", job_types_list)
with col4:
    if job_query_param:
        find_text = job_query_param
    else:
        find_text = ''
    f_text = st.text_input("search text", find_text)

# noinspection PyNoneFunctionAssignment
filtered = df.copy()

if f_action != "(all)" and "action" in filtered.columns:
    filtered = filtered[filtered["action"] == f_action]

if f_phase != "(all)":
    filtered = filtered[filtered["phase"] == f_phase]

if f_job != "(all)":
    filtered = filtered[filtered["job"] == f_job]


if f_text.strip():
    txt = f_text.lower()
    mask = filtered.apply(
        lambda row: row.astype(str).str.lower().str.contains(txt).any(), axis=1
    )
    filtered = filtered[mask]

# ===== Build display DataFrame ===============================================
# 1st col: level
# 2nd: Time
# 3rd: phase
# 4th: Details = comma-separated other fields (key=value)
detail_exclude = {"level_fmt", "Time", "phase", "job", "action"}

detail_cols = [c for c in filtered.columns if c not in detail_exclude]


def build_details(row):
    parts = []
    for c in detail_cols:
        v = row.get(c, "")
        if pd.isna(v) or v == "":
            continue
        if c == 'elapsed':
            v = f'{float(v):.3f}s'
        elif c == 'attempt':
            v = int(v)
        if isinstance(v, str):
            v = repr(v)
        parts.append(f"{c}={v}")
    return ", ".join(parts)


filtered["Details"] = filtered.apply(build_details, axis=1)

display_df = filtered[["level", "Time", "action", "job", "phase", "Details"]].rename(
    columns={
        "level": "Level",
        "phase": "Phase",
        "job": "Job",
        "action": "Action",
    }
)


# ===== Row coloring by level ==================================================
def highlight_level(row):
    level_str = str(row["Level"]).lower()
    base = [""] * len(row)

    if "error" in level_str or "exception" in level_str:
        # light reddish
        return [
            "background-color: rgba(255, 0, 0, 0.12);" for _ in row
        ]
    if "warning" in level_str:
        # light yellowish
        return [
            "background-color: rgba(255, 255, 0, 0.15);" for _ in row
        ]
    return base


styled = display_df.style.apply(highlight_level, axis=1)

# ===== Show result ============================================================
st.write(f"### Logs ({len(display_df)})")
st.dataframe(styled, use_container_width=True, hide_index=True)

# ===== Bar chart ==============================================================
if "date" in filtered.columns and "level" in filtered.columns:
    chart_df = (
        filtered.groupby(["date", "level"])
        .size()
        .reset_index(name="count")
    )

    # Color map
    color_scale = alt.Scale(
        domain=["error", "warning", "info"],
        range=["#ff4d4f", "#fadb14", "#52c41a"]  # red, yellow, green
    )

    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=alt.X("date:T", title="Day"),
            y=alt.Y("count:Q", title="Count"),
            color=alt.Color("level:N", scale=color_scale, title="Level"),
            tooltip=["date:T", "level:N", "count:Q"],
        )
        .properties(height=300)
    )

    st.write("### Daily log levels")
    st.altair_chart(chart, use_container_width=True)
