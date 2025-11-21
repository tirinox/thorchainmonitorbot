import json
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from notify.pub_scheduler import PublicScheduler
from tools.dashboard.helpers import get_app, run_coro

st_autorefresh(interval=2000, key="refresh")
app = get_app()

st.set_page_config(page_title="Scheduler logs", layout="wide")


async def send_reload_confing_message():
    sched: PublicScheduler = app.deps.pub_scheduler
    logs = await sched.db_log.get_last_logs(300)
    return logs


last_logs = run_coro(send_reload_confing_message())

# Convert to DataFrame for table view
df = pd.DataFrame(last_logs)

# Convert timestamps
if "_ts" in df.columns:
    df["_ts"] = df["_ts"].apply(
        lambda x: datetime.fromtimestamp(x).strftime("%Y/%m/%d | %H:%M:%S")[:-3]
    )

# Convert nested dicts → json strings for clean table
for col in df.columns:
    if df[col].dtype == object:
        df[col] = df[col].apply(
            lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v
        )

# ---- Sidebar filters ----

action_list = ["(all)"] + sorted(df["action"].dropna().unique().tolist())
phase_list = ["(all)"] + sorted(df["phase"].dropna().unique().tolist())

f_action = st.selectbox("action", action_list)
f_phase = st.selectbox("phase", phase_list)
f_text = st.text_input("search text", "")

filtered = df.copy()

if f_action != "(all)":
    filtered = filtered[filtered["action"] == f_action]

if f_phase != "(all)":
    filtered = filtered[filtered["phase"] == f_phase]

if f_text.strip():
    txt = f_text.lower()
    mask = filtered.apply(lambda row: row.astype(str).str.lower().str.contains(txt).any(), axis=1)
    filtered = filtered[mask]

# ---- Show result ----
st.write(f"### Logs ({len(filtered)})")
st.dataframe(filtered, use_container_width=True)
