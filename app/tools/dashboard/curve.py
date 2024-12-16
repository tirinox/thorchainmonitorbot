from lib.depcont import DepContainer
from lib.money import DepthCurve
from notify.public.tx_notify import SwapTxNotifier, LiquidityTxNotifier


async def curve_dashboard_info(d: DepContainer):
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    liquidity_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)

    return (
        swap_notifier_tx.dbg_evaluate_curve_for_pools() +
        liquidity_notifier_tx.dbg_evaluate_curve_for_pools()
    )
