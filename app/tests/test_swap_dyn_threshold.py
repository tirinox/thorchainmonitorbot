from types import SimpleNamespace

import pytest

from lib.config import Config
from lib.depcont import DepContainer
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from notify.public.swap_dyn_threshold import DirectionalThreshold, swap_direction
from notify.public.tx_notify import SwapTxNotifier
from lib.money import DepthCurve
from tests.fakes import FakeDB, FakeRedis
from tests.test_streaming_swap_start_notify import make_event

BTC_ETH = swap_direction('BTC.BTC', 'ETH.ETH')
HALF_LIFE = 1800.0


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def make_dyn(growth=0.4, max_bar=50e6):
    clock = Clock()
    return DirectionalThreshold(FakeDB(FakeRedis()), growth, HALF_LIFE, max_bar, clock=clock), clock


def test_direction_merges_forms_of_an_asset():
    assert swap_direction('BTC~BTC', 'ETH/ETH') == 'BTC.BTC>ETH.ETH'
    assert swap_direction('ETH.ETH', 'BTC.BTC') != BTC_ETH


@pytest.mark.asyncio
async def test_bar_rises_with_each_swap_and_blocks_equal_ones():
    dyn, _ = make_dyn()
    assert await dyn.check_and_record(BTC_ETH, 500_000)  # 500k -> bar 700k
    assert await dyn.current_bar(BTC_ETH) == pytest.approx(700_000)

    # 14 more of the same size: none passes
    for _ in range(14):
        assert not await dyn.check_and_record(BTC_ETH, 500_000)
    assert await dyn.current_bar(BTC_ETH) == pytest.approx(700_000)

    assert await dyn.check_and_record(BTC_ETH, 750_000)  # a bigger one passes and lifts the bar to 1.05M
    assert await dyn.current_bar(BTC_ETH) == pytest.approx(1_050_000)
    snap = (await dyn.snapshot())[0]
    assert snap['count'] == 2 and snap['last_volume_usd'] == 750_000


@pytest.mark.asyncio
async def test_bar_cools_down_by_half_life():
    dyn, clock = make_dyn()
    await dyn.record(BTC_ETH, 500_000)
    clock.t += HALF_LIFE
    assert await dyn.current_bar(BTC_ETH) == pytest.approx(350_000)
    assert await dyn.passes(BTC_ETH, 400_000)

    clock.t += 40 * HALF_LIFE
    assert await dyn.snapshot() == []  # cooled, gone from the list
    await dyn.record(BTC_ETH, 10_000)
    assert (await dyn.snapshot())[0]['count'] == 1  # a new series


@pytest.mark.asyncio
async def test_directions_are_independent_and_capped():
    dyn, _ = make_dyn(max_bar=1_000_000)
    await dyn.record(BTC_ETH, 500_000)
    assert await dyn.passes(swap_direction('ETH.ETH', 'BTC.BTC'), 1)
    await dyn.record(BTC_ETH, 5_000_000)
    assert await dyn.current_bar(BTC_ETH) == 1_000_000


@pytest.mark.asyncio
async def test_reset():
    dyn, _ = make_dyn()
    await dyn.record(BTC_ETH, 500_000)
    await dyn.record('A>B', 500_000)
    assert await dyn.reset(BTC_ETH) is True
    assert await dyn.reset(BTC_ETH) is False
    assert await dyn.passes(BTC_ETH, 1)
    assert await dyn.reset_all() == 1
    assert await dyn.snapshot() == []


def test_from_config_is_off_by_default():
    cfg = Config(data={'tx': {'swap': {}}})
    assert DirectionalThreshold.from_config(FakeDB(FakeRedis()), cfg) is None
    cfg = Config(data={'tx': {'swap': {'dynamic_threshold': {'enabled': True, 'growth': 0.5, 'half_life': '10m'}}}})
    dyn = DirectionalThreshold.from_config(FakeDB(FakeRedis()), cfg)
    assert dyn.growth == 0.5 and dyn.half_life_sec == 600


# ---------- notifiers ----------

@pytest.mark.asyncio
async def test_start_notifier_lets_through_one_of_a_series():
    from tests.test_streaming_swap_start_notify import make_deps
    deps = make_deps()
    notifier = StreamingSwapStartTxNotifier(deps)
    notifier.dyn_threshold, _ = make_dyn()
    notifier.dyn_threshold.db = deps.db
    notifier.load_extra_tx_information = _noop
    passed = []
    notifier.add_subscriber(SimpleNamespace(on_data=_collect(passed)))

    for i in range(5):
        await notifier.on_data(None, make_event(tx_id=f'tx{i}', volume_usd=500_000.0))
    assert [e.tx_id for e in passed] == ['tx0']

    await notifier.on_data(None, make_event(tx_id='big', volume_usd=800_000.0))
    assert [e.tx_id for e in passed] == ['tx0', 'big']


def _collect(out):
    async def on_data(sender, event):
        out.append(event)

    return on_data


async def _noop(event):
    return event


def make_swap_notifier(dyn_enabled=True):
    d = DepContainer()
    d.db = FakeDB(FakeRedis())
    data = {'tx': {'max_age': '0', 'swap': {
        'min_usd_total': 50, 'curve_mult': 0.3, 'dynamic_threshold': {'enabled': dyn_enabled},
        'also_trigger_when': {'streaming_swap': {'volume_greater': 1000}},
    }}}
    d.cfg = Config(data=data)
    n = SwapTxNotifier(d, d.cfg.tx.swap, curve=DepthCurve.default())
    return n


def make_tx(tx_hash, volume_rune):
    return SimpleNamespace(
        tx_hash=tx_hash,
        first_input_tx=SimpleNamespace(first_asset='BTC.BTC'),
        recipients_output=SimpleNamespace(first_asset='ETH.ETH'),
        full_volume_in_rune=volume_rune,
    )


@pytest.mark.asyncio
async def test_finish_notifier_gate_and_announced_start():
    n = make_swap_notifier()
    ph = SimpleNamespace(usd_per_rune=2.0)

    assert await n._clears_dynamic_threshold(make_tx('a', 250_000), ph)  # 500k$, bar -> 700k$
    assert not await n._clears_dynamic_threshold(make_tx('b', 250_000), ph)
    assert await n.deduplicator.have_ever_seen_hash('b')  # blocked for good

    # is_tx_suitable: a finish whose start was announced is not touched by the bar
    async def static_ok(*a, **k):
        return True

    n._is_tx_suitable_statically = static_ok
    n._ss_txs_started = {'c'}
    assert await n.is_tx_suitable(make_tx('c', 10), 0, ph)
    assert not await n.is_tx_suitable(make_tx('d', 250_000), 0, ph)
    assert await n.is_tx_suitable(make_tx('e', 400_000), 0, ph)  # 800k$


@pytest.mark.asyncio
async def test_finish_notifier_without_dynamic_threshold_is_unchanged():
    n = make_swap_notifier(dyn_enabled=False)
    assert n.dyn_threshold is None
    ph = SimpleNamespace(usd_per_rune=2.0)
    assert await n._clears_dynamic_threshold(make_tx('a', 250_000), ph)
    assert await n._clears_dynamic_threshold(make_tx('b', 250_000), ph)
