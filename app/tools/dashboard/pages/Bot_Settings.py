import streamlit as st

from lib.date_utils import now_ts, format_time_ago
from lib.flagship import Flagship, FlagDescriptor
from tools.dashboard.helpers import get_app, run_coro

app = get_app()
st.set_page_config(page_title="Bot Settings", layout="wide")


async def set_flag_value(path: str, new_value: bool):
    flagship: Flagship = app.deps.flagship
    await flagship.set_flag(path, new_value)


def on_toggle_changed(path: str, state_key: str):
    new_value = bool(st.session_state[state_key])

    st.toast(f"Set {path} = {new_value}", icon="🧪")
    run_coro(set_flag_value(path, new_value))


now = now_ts()


# ----------------------------
# Recursive renderer
# ----------------------------
def render_node(node, path_parts: list[str], expanded):
    if isinstance(node, dict):
        for key in sorted(node.keys(), key=str):
            value = node[key]
            new_path = path_parts + [str(key)]

            if isinstance(value, FlagDescriptor):
                path = value.full_path or ":".join(new_path)
                state_key = f"flag:{path}"

                # initialize session state once
                if state_key not in st.session_state:
                    st.session_state[state_key] = value.value

                c1, c2, c4, c3 = st.columns([6, 1, 1, 4])

                with c1:
                    st.write(path)

                with c2:
                    st.toggle(
                        "On",
                        key=state_key,
                        on_change=on_toggle_changed,
                        kwargs={
                            "path": path,
                            "state_key": state_key,
                        },
                        label_visibility="collapsed",
                    )

                with c3:
                    # delete button
                    if st.button("Delete", key=f"del:{path}", help="Delete this flag from the database"):
                        st.toast(f"Deleted flag {path}", icon="🗑️")
                        run_coro(app.deps.flagship.delete_flag(path))
                        st.session_state.pop(state_key, None)
                        # Rerun to refresh UI
                        st.rerun()
                with c4:
                    st.caption(
                        f"changed: {format_time_ago(now - value.last_changed_ts)} · "
                        f"access: {format_time_ago(now - value.last_access_ts)}"
                    )

            else:
                # Nested object
                with st.expander(str(key), expanded=expanded):
                    render_node(value, new_path, expanded)

    else:
        st.write(node)


# ----------------------------
# Load hierarchy
# ----------------------------
async def load_flagship_hierarchy():
    flagship: Flagship = app.deps.flagship
    return await flagship.get_all_hierarchy()


# ----------------------------
# UI
# ----------------------------
st.header("Bot Settings")
st.subheader("Connection gate matrix")

hierarchy = run_coro(load_flagship_hierarchy())


def get_stats(node):
    total, total_off, total_on = 0, 0, 0
    if isinstance(node, dict):
        for value in node.values():
            t, toff, ton = get_stats(value)
            total += t
            total_off += toff
            total_on += ton
    elif isinstance(node, FlagDescriptor):
        total = 1
        if node.value:
            total_on = 1
        else:
            total_off = 1
    return total, total_off, total_on


def print_stats(node):
    total, total_off, total_on = get_stats(node)
    # metrics:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total flags", total)
    with col2:
        st.metric("Enabled", total_on)
    with col3:
        st.metric("Disabled", total_off)


# optional: nice tabs at root level
if isinstance(hierarchy, dict):
    print_stats(hierarchy)
    everything_expanded = st.checkbox("Expand all", value=True)
    tabs = st.tabs(list(hierarchy.keys()))
    for tab, key in zip(tabs, hierarchy.keys()):
        with tab:
            st.text("Tab stats:")
            print_stats(hierarchy[key])
            render_node(hierarchy[key], [key], everything_expanded)

else:
    st.error("Hierarchy is not a dict")
    st.write(hierarchy)
