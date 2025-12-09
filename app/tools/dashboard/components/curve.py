import streamlit as st

from lib.money import DepthCurve
from notify.public.tx_notify import SwapTxNotifier, LiquidityTxNotifier
from tools.dashboard.helpers import run_coro


async def curve_dashboard_info_async(app, swap_notifier_tx=None, liquidity_notifier_tx=None):
    d = app.deps
    ph = await d.pool_cache.get()
    swap_curve_info = swap_notifier_tx.dbg_evaluate_curve_for_pools(ph, silent=True)
    liq_curve_info = liquidity_notifier_tx.dbg_evaluate_curve_for_pools(ph, silent=True)
    return swap_curve_info + liq_curve_info


def curve_dashboard_info(app):
    st.subheader('Curve')

    d = app.deps
    if 'swap_notifier_tx' not in st.session_state:
        curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
        curve = DepthCurve(curve_pts)
        st.session_state['swap_notifier_tx'] = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
        st.session_state['liquidity_notifier_tx'] = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)

    data = run_coro(curve_dashboard_info_async(app,
                                               st.session_state['swap_notifier_tx'],
                                               st.session_state['liquidity_notifier_tx']))
    st.table(data)
