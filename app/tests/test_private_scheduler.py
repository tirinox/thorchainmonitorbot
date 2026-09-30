from types import SimpleNamespace

import pytest

import lib.scheduler as scheduler_module
from lib.date_utils import DAY, HOUR, MINUTE
from lib.delegates import INotified
from lib.scheduler import PrivateScheduler
from lib.settings_manager import GeneralSettings
from notify.personal.scheduled import PersonalPeriodicNotificationService, PersonalIdTriplet
from tests.fakes import FakeRedis, FakeDB

T0 = 1_700_000_000.0


class FakeZSetRedis(FakeRedis):
    def __init__(self):
        super().__init__()
        self.zsets = {}

    async def zadd(self, name, mapping, xx=False, nx=False):
        zset = self.zsets.setdefault(name, {})
        added = 0
        for member, score in mapping.items():
            if (xx and member not in zset) or (nx and member in zset):
                continue
            added += member not in zset
            zset[member] = float(score)
        return added

    async def zrangebyscore(self, name, min_score, max_score, withscores=False):
        items = sorted((score, member) for member, score in self.zsets.get(name, {}).items()
                       if min_score <= score <= max_score)
        return [(member, score) if withscores else member for score, member in items]

    async def zrange(self, name, start, end, withscores=False):
        return await self.zrangebyscore(name, float('-inf'), float('inf'), withscores)

    async def zscore(self, name, member):
        return self.zsets.get(name, {}).get(member)

    async def zrem(self, name, *members):
        zset = self.zsets.get(name, {})
        return sum(zset.pop(member, None) is not None for member in members)


class Recorder(INotified):
    def __init__(self):
        self.received = []

    async def on_data(self, sender, data):
        self.received.append(data)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = Clock(T0)
    monkeypatch.setattr(scheduler_module, 'now_ts', c)
    return c


@pytest.fixture
def sched():
    s = PrivateScheduler(FakeZSetRedis(), 'Test', poll_interval=60)
    s.recorder = Recorder()
    s.add_subscriber(s.recorder)
    return s


@pytest.mark.asyncio
async def test_periodic_event_fires_and_keeps_phase(sched, clock):
    await sched.schedule('sub', period=DAY)

    clock.t = T0 + DAY + 50  # polled a bit later than due
    await sched._process()

    assert sched.recorder.received == ['sub']
    assert await sched.get_next_timestamp('sub') == T0 + 2 * DAY


@pytest.mark.asyncio
async def test_periodic_event_survives_long_downtime(sched, clock):
    await sched.schedule('sub', period=DAY)

    # the bot was down for 3 days
    clock.t = T0 + 4 * DAY
    await sched._process()

    # no burst right away, but the subscription is still there and catches up soon
    assert sched.recorder.received == []
    catch_up_ts = await sched.get_next_timestamp('sub')
    assert clock.t <= catch_up_ts <= clock.t + sched.catch_up_spread
    assert await sched.get_period('sub')

    clock.t = catch_up_ts + 30
    await sched._process()

    # exactly one catch-up report, then the regular schedule goes on
    assert sched.recorder.received == ['sub']
    assert await sched.get_next_timestamp('sub') == catch_up_ts + DAY


@pytest.mark.asyncio
async def test_downtime_shorter_than_spread_skips_missed_slots(sched, clock):
    await sched.schedule('sub', period=10 * MINUTE)

    clock.t = T0 + 10 * MINUTE + 25 * MINUTE  # two slots missed, still within the spread
    await sched._process()

    assert sched.recorder.received == ['sub']
    assert await sched.get_next_timestamp('sub') == T0 + 40 * MINUTE


@pytest.mark.asyncio
async def test_event_is_kept_when_handler_fails_before_rescheduling(sched, clock):
    await sched.schedule('sub', period=DAY)

    async def broken_get_period(ident):
        raise ConnectionError('redis is down')

    sched.get_period = broken_get_period
    clock.t = T0 + DAY + 10
    await sched._process()
    assert await sched.get_next_timestamp('sub') == T0 + DAY

    del sched.get_period
    clock.t = T0 + DAY + 70
    await sched._process()
    assert sched.recorder.received == ['sub']
    assert await sched.get_next_timestamp('sub') == T0 + 2 * DAY


@pytest.mark.asyncio
async def test_one_shot_event_fires_once(sched, clock):
    await sched.schedule('once', timestamp=T0 + HOUR)

    clock.t = T0 + HOUR + 10
    await sched._process()
    await sched._process()

    assert sched.recorder.received == ['once']
    assert await sched.get_next_timestamp('once') is None


@pytest.mark.asyncio
async def test_one_shot_event_is_forgotten_after_long_delay(sched, clock):
    await sched.schedule('once', timestamp=T0 + HOUR)

    clock.t = T0 + HOUR + DAY + 1
    await sched._process()

    assert sched.recorder.received == []
    assert await sched.get_next_timestamp('once') is None


@pytest.mark.asyncio
async def test_cancelled_event_is_not_resurrected(sched, clock):
    await sched.schedule('sub', period=DAY)
    await sched.cancel('sub')

    clock.t = T0 + 2 * DAY
    await sched._process()

    assert sched.recorder.received == []
    assert await sched.get_next_timestamp('sub') is None


@pytest.mark.asyncio
async def test_negative_period_cancels_event(sched, clock):
    await sched.schedule('sub', period=DAY)
    await sched._r.set(sched.key_period('sub'), -1)

    clock.t = T0 + DAY + 10
    await sched._process()

    assert sched.recorder.received == []
    assert await sched.get_next_timestamp('sub') is None


def test_next_slot():
    assert PrivateScheduler.next_slot(100, 100, 10) == 110
    assert PrivateScheduler.next_slot(100, 105, 10) == 110
    assert PrivateScheduler.next_slot(100, 110, 10) == 120
    assert PrivateScheduler.next_slot(100, 135, 10) == 140


async def make_lost_event(sched, ident, period=DAY):
    # what the old scheduler left behind: the period key without the timeline entry
    await sched._r.set(sched.key_period(ident), period)


@pytest.mark.asyncio
async def test_restore_lost_periodic_events(sched, clock):
    await make_lost_event(sched, 'lost')
    await sched.schedule('alive', period=DAY)
    await sched._r.set(sched.key_period('cancelled'), -1)

    restored = await sched.restore_lost_periodic()

    assert restored == ['lost']
    ts = await sched.get_next_timestamp('lost')
    assert clock.t <= ts <= clock.t + sched.catch_up_spread
    assert await sched.get_next_timestamp('alive') == T0 + DAY
    assert await sched.get_next_timestamp('cancelled') is None

    # restoring again changes nothing
    assert await sched.restore_lost_periodic() == []
    assert await sched.get_next_timestamp('lost') == ts

    # the restored event then works as a regular subscription
    clock.t = ts + 30
    await sched._process()
    assert sched.recorder.received == ['lost']
    assert await sched.get_next_timestamp('lost') == ts + DAY


@pytest.mark.asyncio
async def test_restore_respects_filter(sched, clock):
    await make_lost_event(sched, 'good')
    await make_lost_event(sched, 'bad')
    await make_lost_event(sched, 'broken')

    async def should_restore(ident):
        if ident == 'broken':
            raise ValueError('cannot parse')
        return ident == 'good'

    sched.should_restore = should_restore

    assert await sched.restore_lost_periodic() == ['good']
    assert await sched.get_next_timestamp('bad') is None
    assert await sched.get_next_timestamp('broken') is None
    # skipped ones are kept, so they can come back later
    assert await sched.get_period('bad')


class FakeSettingsManager:
    def __init__(self, settings):
        self.settings = settings

    async def get_settings(self, channel_id):
        return self.settings.get(channel_id, {})


@pytest.mark.asyncio
async def test_personal_service_does_not_restore_inactive_users():
    settings_manager = FakeSettingsManager({
        '111': {GeneralSettings.INACTIVE: True},
        '222': {GeneralSettings.INACTIVE: False},
    })
    service = PersonalPeriodicNotificationService(SimpleNamespace(db=FakeDB(), settings_manager=settings_manager))

    assert not await service.should_restore(PersonalIdTriplet('111', 'thor1abc', 'BTC.BTC').as_key)
    assert await service.should_restore(PersonalIdTriplet('222', 'thor1abc', 'BTC.BTC').as_key)
    assert await service.should_restore(PersonalIdTriplet('333', 'thor1abc', 'ETH.USDC-0XA0B8').as_key)
