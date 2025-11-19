import asyncio
import logging
import threading

import streamlit as st

from tools.lib.lp_common import LpAppFramework

_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def get_background_loop() -> asyncio.AbstractEventLoop:
    """Get (or create) a single background event loop."""
    global _loop, _loop_thread

    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()

            def _run_loop():
                asyncio.set_event_loop(_loop)
                _loop.run_forever()

            _loop_thread = threading.Thread(target=_run_loop, daemon=True)
            _loop_thread.start()

    return _loop


def run_coro(coro):
    """
    Run a coroutine on the background loop and wait for the result
    in a blocking way (safe to call from Streamlit).
    """
    loop = get_background_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()  # you may want try/except here and re-raise nicely


@st.cache_resource
def get_app():
    async def _get_app():
        app = LpAppFramework(log_level=logging.INFO)
        await app.prepare(brief=True)
        return app

    return run_coro(_get_app())
