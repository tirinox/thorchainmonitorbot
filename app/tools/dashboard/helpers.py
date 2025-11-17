import asyncio
import logging

import streamlit as st

from tools.lib.lp_common import LpAppFramework

# A dictionary to store ongoing tasks
tasks = {}

# Ensure there is a running event loop
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


# Define a helper function to create and schedule async tasks
def schedule_task(key, coro):
    """Schedules an async task and stores it with a unique key."""
    if key not in tasks:
        tasks[key] = loop.create_task(coro)


# Run the event loop to process scheduled tasks
def process_tasks():
    """Process pending tasks on the event loop."""
    pending = [task for task in tasks.values() if not task.done()]
    if pending:
        loop.run_until_complete(asyncio.gather(*pending))


def run_task(coro):
    """Run a coroutine and return its result."""
    task = loop.create_task(coro)
    return loop.run_until_complete(task)

@st.cache_resource
def get_app():
    async def _get_app():
        app = LpAppFramework(log_level=logging.INFO)
        await app.prepare(brief=True)
        return app
    return run_task(_get_app())
