from typing import cast

import pytest

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from comm.localization.twitter_eng import TwitterEnglishLocalization
from lib.config import Config, SubConfig
from lib.date_utils import DAY, HOUR, now_ts
from lib.db import DB
from lib.depcont import DepContainer
from lib.rate_limit import SlidingWindowLimiter
from models.mimir import MimirChange, MimirEntry
from notify.public.mimir_notify import MimirChangedNotifier
from tests.fakes import FakeDB, FakeRedis

T0 = 1_800_000_000.0


def make_db() -> DB:
    return cast(DB, cast(object, FakeDB(FakeRedis())))


@pytest.mark.asyncio
async def test_sliding_window_strict_cap_within_period():
    limiter = SlidingWindowLimiter(make_db(), 'Test', limit=3, period=DAY)

    for i in range(3):
        assert await limiter.free_at(T0 + i) == T0 + i
        assert await limiter.hit(T0 + i)

    # unlike GCRA, no extra hits are let through anywhere inside the window
    assert not await limiter.hit(T0 + 3)
    assert not await limiter.hit(T0 + DAY - 1)
    assert await limiter.free_at(T0 + 10) == T0 + DAY

    # the oldest hit slides out, one slot frees up
    assert await limiter.hit(T0 + DAY + 0.5)
    assert not await limiter.hit(T0 + DAY + 0.7)
    assert await limiter.free_at(T0 + DAY + 0.8) == T0 + 1 + DAY


@pytest.mark.asyncio
async def test_sliding_window_disabled_and_clear():
    db = make_db()
    unlimited = SlidingWindowLimiter(db, 'Test', limit=0, period=DAY)
    for i in range(100):
        assert await unlimited.hit(T0 + i)
    assert await unlimited.free_at(T0) == T0

    limiter = SlidingWindowLimiter(db, 'Test2', limit=1, period=DAY)
    assert await limiter.hit(T0)
    assert not await limiter.hit(T0 + 1)
    await limiter.clear()
    assert await limiter.hit(T0 + 2)


def make_notifier(max_per_day=10, max_hits_before_cd=100) -> MimirChangedNotifier:
    deps = DepContainer()
    deps.db = make_db()
    deps.cfg = SubConfig({
        'constants': {
            'mimir_change': {
                'cooldown': '20m',
                'max_hits_before_cd': max_hits_before_cd,
                'max_per_day': max_per_day,
            }
        }
    })
    return MimirChangedNotifier(deps)


def make_change(name='HALTSIGNINGBTC', ts=T0, old='0', new='1') -> MimirChange:
    entry = MimirEntry(name, 'Halt BTC Signing', new, None, 0, 'bool', MimirEntry.SOURCE_ADMIN)
    return MimirChange(MimirChange.VALUE_CHANGE, name, old, new, entry, ts)


@pytest.mark.asyncio
async def test_flapping_halt_is_capped_per_day_and_per_key():
    notifier = make_notifier(max_per_day=10)

    passed = []
    for i in range(30):
        change = make_change(ts=T0 + i * 20 * 60, old=str(i % 2), new=str((i + 1) % 2))
        if await notifier._will_pass(change):
            passed.append(change)

    assert len(passed) == 10
    # only the alert that used the last slot carries the mute note
    assert all(not c.muted_until for c in passed[:-1])
    assert passed[-1].muted_until == T0 + DAY

    # another halt key has its own budget
    assert await notifier._will_pass(make_change(name='HALTETHCHAIN', ts=T0 + 10 * HOUR))

    # a day after the first alert, the key is reported again
    assert await notifier._will_pass(make_change(ts=T0 + DAY + 1))


@pytest.mark.asyncio
async def test_daily_limit_zero_means_unlimited():
    notifier = make_notifier(max_per_day=0)
    for i in range(30):
        change = make_change(ts=T0 + i * 60, old=str(i % 2), new=str((i + 1) % 2))
        assert await notifier._will_pass(change)
        assert not change.muted_until


@pytest.mark.asyncio
async def test_burst_cooldown_does_not_spend_daily_budget():
    # the burst cooldown blocks after 2 hits; blocked changes must not eat the daily budget
    notifier = make_notifier(max_per_day=3, max_hits_before_cd=2)
    results = [await notifier._will_pass(make_change(ts=T0 + i)) for i in range(5)]
    assert results == [True, True, False, False, False]

    limiter = SlidingWindowLimiter(notifier.deps.db, 'MimirChange:Daily:HALTSIGNINGBTC', 3, DAY)
    assert len(await limiter.get_hits(T0 + 10)) == 2


@pytest.mark.parametrize('loc_class', [EnglishLocalization, RussianLocalization, TwitterEnglishLocalization])
def test_mimir_change_text_mentions_mute(loc_class):
    loc = loc_class(Config(name='./tests/test_config.yaml'))

    class _Rules:
        @staticmethod
        def get_mimir_units(_key):
            return None

    class _Holder:
        last_thor_block = 0

    loc.mimir_rules = _Rules()

    change = make_change()
    plain = loc.notification_text_mimir_changed([change], _Holder())
    assert '⚠️' not in plain

    change.muted_until = now_ts() + 5 * HOUR
    muted = loc.notification_text_mimir_changed([change], _Holder())
    assert '⚠️' in muted
    assert muted.startswith(plain.split('\n\n')[0])
