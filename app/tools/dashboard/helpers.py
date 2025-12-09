import asyncio
import atexit
import logging
import threading

import streamlit as st

from tools.lib.lp_common import LpAppFramework


async def _startup():
    pass


async def _shutdown():
    pass


@st.cache_resource  # <----- this is what makes it possible to keep an event loop alive across multiple script runs (CTA clicks).
def get_global_loop(startup=_startup, shutdown=_shutdown):
    """
    Returns a persistent asyncio loop running in a background thread.
    The loop will live across Streamlit reruns and only be cleaned up at shutdown.
    """
    loop = asyncio.new_event_loop()

    def run_loop():
        loop.create_task(startup())
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    def stop_loop():
        try:
            fut = asyncio.run_coroutine_threadsafe(shutdown(), loop)
            fut.result(timeout=5)
        except Exception as e:
            print(f"[shutdown] Error during cleanup: {e}")
        # noinspection PyTypeChecker
        loop.call_soon_threadsafe(loop.stop)

    atexit.register(stop_loop)

    return loop


def run_coro(coro):
    """
    Run a coroutine on the background loop and wait for the result
    in a blocking way (safe to call from Streamlit).
    """
    loop = get_global_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()  # you may want try/except here and re-raise nicely


@st.cache_resource
def get_app():
    loop = get_global_loop()

    async def _get_app():
        app = LpAppFramework(log_level=logging.INFO)
        app.deps.data_controller.enabled = False
        app.deps.loop = loop
        await app.prepare()
        # noinspection PyProtectedMember
        await app.deps.pub_scheduler.start_rpc_client()
        print("🍑 App initialized ")
        return app

    return run_coro(_get_app())


def st_running_sign():
    st.markdown("""
    <style>
    .blink {
      animation: blinker 1s linear infinite;
      color: red;
      font-weight: bold;
      font-size: 20px;
    }
    @keyframes blinker {  
      50% { opacity: 0; }
    }
    </style>

    <p class="blink">🚀Running...</p>
    """, unsafe_allow_html=True)
