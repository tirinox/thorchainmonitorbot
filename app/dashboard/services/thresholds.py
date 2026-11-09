import math
from typing import Optional

from dashboard.audit import AuditAction, LOCAL_ACTOR
from dashboard.context import DashboardContext
from lib.date_utils import now_ts
from notify.public.swap_dyn_threshold import COOLED_BAR_USD


def _static_finish_usd(notifier, ph, direction: str) -> float:
    """What a swap of this direction must be worth to be announced by the regular rule: min_usd_total or the share of
    the shallowest pool on the route by the depth curve, the larger. (Streaming, DEX, affiliate and trade asset swaps
    have rules of their own, they are in `static`.)"""
    in_asset, out_asset = direction.split('>')
    pool = ph.shallowest_pool_on_route(in_asset, out_asset) if ph and ph.usd_per_rune else None
    share_usd = 0.0
    if pool and notifier.curve:
        depth = pool.usd_depth(ph.usd_per_rune)
        share_usd = depth * notifier.curve.evaluate(depth) * notifier.curve_mult
    return max(float(notifier.min_usd_total), share_usd)


async def get_thresholds(ctx: DashboardContext) -> dict:
    n = ctx.swap_notifier
    dyn = n.dyn_threshold
    static = {
        'start_usd': n.min_streaming_swap_usd,
        'finish_min_usd_total': n.min_usd_total,
        'curve_mult': n.curve_mult,
        'dex_usd': n.dex_min_usd,
        'affiliate_fee_usd': n.aff_fee_min_usd,
        'trade_asset_usd': n.min_trade_asset_swap_usd,
    }
    result = {
        'enabled': dyn is not None,
        'static': static,
        'config': {'growth': dyn.growth, 'half_life_sec': dyn.half_life_sec, 'max_bar_usd': dyn.max_bar_usd}
        if dyn else None,
        'directions': [],
    }
    if not dyn:
        return result

    ph = await ctx.deps.pool_cache.get()
    now = now_ts()
    for item in await dyn.snapshot():
        static_finish = _static_finish_usd(n, ph, item['direction'])
        # "back to normal" is when the bar is under both static thresholds
        normal = max(min(static['start_usd'], static_finish), COOLED_BAR_USD)
        bar = item['bar_usd']
        cools_at = now + dyn.half_life_sec * math.log2(bar / normal) if bar > normal else None
        result['directions'].append({
            **item,
            'static_start_usd': static['start_usd'],
            'static_finish_usd': static_finish,
            'effective_start_usd': max(static['start_usd'], bar),
            'effective_finish_usd': max(static_finish, bar),
            'cools_at_ts': cools_at,
        })
    return result


async def reset_thresholds(ctx: DashboardContext, direction: Optional[str], actor: str = LOCAL_ACTOR) -> dict:
    """Drops the dynamic bar of one direction, or of all of them if `direction` is None."""
    dyn = ctx.swap_notifier.dyn_threshold
    if not dyn:
        raise ValueError('The dynamic threshold is turned off in the config')
    if direction:
        n = int(await dyn.reset(direction))
    else:
        n = await dyn.reset_all()
    await ctx.audit.record(AuditAction.THRESHOLD_RESET, actor, direction or '*', reset=n)
    return {'ok': True, 'reset': n}
