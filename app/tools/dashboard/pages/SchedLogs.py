import json
from datetime import datetime

import pandas as pd
import streamlit as st
from eth_utils import humanize_seconds
from streamlit_autorefresh import st_autorefresh

from notify.pub_scheduler import PublicScheduler
from tools.dashboard.helpers import get_app, run_coro

st.set_page_config(page_title="Scheduler logs", layout="wide")
st_autorefresh(interval=2000, key="refresh")

app = get_app()


# ===== Data loading ===========================================================
async def fetch_logs():
    sched: PublicScheduler = app.deps.pub_scheduler
    logs = await sched.db_log.get_last_logs(300)
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

# Timestamp → Time column
if "_ts" in df.columns:
    now = datetime.now().timestamp()
    df["Time"] = df["_ts"].apply(
        lambda x: f'{datetime.fromtimestamp(x).strftime("%Y/%m/%d | %H:%M:%S")} | {humanize_seconds(now - x)} ago'
        if pd.notna(x)
        else ""
    )
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

df["level"] = df["level"].apply(format_level)

# Ensure phase exists
if "phase" not in df.columns:
    df["phase"] = ""


# ===== Filters (use raw columns, not the final 4-column view) ================
action_list = ["(all)"]
if "action" in df.columns:
    action_list += sorted(df["action"].dropna().unique().tolist())

phase_list = ["(all)"] + sorted(df["phase"].dropna().unique().tolist())

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    f_action = st.selectbox("action", action_list)
with col2:
    f_phase = st.selectbox("phase", phase_list)
with col3:
    f_text = st.text_input("search text", "")

filtered = df.copy()

if f_action != "(all)" and "action" in filtered.columns:
    filtered = filtered[filtered["action"] == f_action]

if f_phase != "(all)":
    filtered = filtered[filtered["phase"] == f_phase]

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
detail_exclude = {"level", "Time", "phase"}

detail_cols = [c for c in filtered.columns if c not in detail_exclude]

def build_details(row):
    parts = []
    for c in detail_cols:
        v = row.get(c, "")
        if pd.isna(v) or v == "":
            continue
        parts.append(f"{c}={v}")
    return ", ".join(parts)

filtered["Details"] = filtered.apply(build_details, axis=1)

display_df = filtered[["level", "Time", "phase", "Details"]].rename(
    columns={
        "level": "Level",
        "phase": "Phase",
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
