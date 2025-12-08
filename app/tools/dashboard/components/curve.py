import streamlit as st

from lib.depcont import DepContainer
from lib.money import DepthCurve
from notify.public.tx_notify import SwapTxNotifier, LiquidityTxNotifier
from tools.dashboard.helpers import run_coro


async def curve_dashboard_info_async(app):
    d = app.deps
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    liquidity_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)

    ph = await d.pool_cache.get()

    return (
        swap_notifier_tx.dbg_evaluate_curve_for_pools(ph) +
        liquidity_notifier_tx.dbg_evaluate_curve_for_pools(ph)
    )


def curve_dashboard_info(app):
    st.subheader('Curve')
    data = run_coro(curve_dashboard_info_async(app))
    st.table(data)
