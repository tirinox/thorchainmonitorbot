import streamlit as st

from jobs.scanner.native_scan import BlockScanner
from lib.depcont import DepContainer
from tools.dashboard.helpers import run_coro


async def block_scanner_info_async(app):
    d: DepContainer = app.deps
    last_block = await d.last_block_cache.get_thor_block()
    scanner: BlockScanner = d.block_scanner
    current_scanner_block = scanner.last_block
    return {
        'last_block': last_block,
        'scanner_block': current_scanner_block,
        'blocks_behind': last_block - current_scanner_block,
        'scanner_last_ts': scanner.last_block_ts
    }


def block_scanner_info(app):
    st.subheader('Block scanner')
    data = run_coro(block_scanner_info_async(app))
    st.warning("In development")

    st.table(data)
