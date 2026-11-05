from types import SimpleNamespace

import pytest

from dashboard.audit import AuditLog
from dashboard.services import thresholds as svc
from notify.public.swap_dyn_threshold import DirectionalThreshold, swap_direction
from tests.fakes import FakeDB, FakePoolCache, FakePubSubRedis, make_price_holder
from tests.test_swap_dyn_threshold import make_swap_notifier, Clock, HALF_LIFE

BTC_ETH = swap_direction('BTC.BTC', 'ETH.ETH')


def make_ctx(enabled=True):
    notifier = make_swap_notifier(dyn_enabled=enabled)
    db = FakeDB(FakePubSubRedis())
    if enabled:
        notifier.dyn_threshold = DirectionalThreshold(db, 0.4, HALF_LIFE, 50e6)
    return SimpleNamespace(swap_notifier=notifier, audit=AuditLog(db),
                           deps=SimpleNamespace(pool_cache=FakePoolCache(make_price_holder())))


@pytest.mark.asyncio
async def test_thresholds_page_data_and_reset():
    ctx = make_ctx()
    assert (await svc.get_thresholds(ctx))['directions'] == []

    await ctx.swap_notifier.dyn_threshold.record(BTC_ETH, 500_000)
    data = await svc.get_thresholds(ctx)
    assert data['enabled'] and data['config']['growth'] == 0.4
    row = data['directions'][0]
    assert row['direction'] == BTC_ETH and row['bar_usd'] == pytest.approx(700_000)
    assert row['static_start_usd'] == 1000 and row['static_finish_usd'] >= 50  # the config of make_swap_notifier
    assert row['effective_start_usd'] == row['effective_finish_usd'] == pytest.approx(700_000)
    assert row['cools_at_ts'] > row['ts']

    assert (await svc.reset_thresholds(ctx, BTC_ETH, actor='bob'))['reset'] == 1
    assert (await svc.get_thresholds(ctx))['directions'] == []


@pytest.mark.asyncio
async def test_thresholds_turned_off():
    ctx = make_ctx(enabled=False)
    data = await svc.get_thresholds(ctx)
    assert data['enabled'] is False and data['directions'] == []
    with pytest.raises(ValueError):
        await svc.reset_thresholds(ctx, None)
