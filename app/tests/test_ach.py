from jobs.achievement.ach_list import A, Achievement
from jobs.achievement.tracker import AchievementsTracker


def meet(key, value, spec='', descending=False):
    return AchievementsTracker.meet_threshold(
        Achievement(key, value, specialization=spec, descending=descending)
    )


def test_minimum_threshold():
    assert meet(A.DAU, 300)
    assert meet(A.DAU, 301)
    assert not meet(A.DAU, 299)

    assert meet(A.COIN_MARKET_CAP_RANK, 41, descending=True)
    assert meet(A.COIN_MARKET_CAP_RANK, 42, descending=True)
    assert not meet(A.COIN_MARKET_CAP_RANK, 43, descending=True)
    assert not meet(A.COIN_MARKET_CAP_RANK, 5000, descending=True)


def test_minimum_threshold_per_pool(per_pool_key):
    from tests.conftest import USDC

    assert meet(per_pool_key, 3_605_512.364805, spec=USDC)
    assert not meet(per_pool_key, 3_500_000, spec=USDC)
    assert meet(per_pool_key, 10_700_000, spec=USDC)

    # a pool without its own threshold has none
    assert meet(per_pool_key, 1, spec='unk')
    assert meet(per_pool_key, 400, spec='unk')


def _block_keys(now):
    from jobs.achievement.extractor import AchievementsExtractor
    from jobs.fetch.cached.last_block import EventLastBlock
    events = AchievementsExtractor.on_block(EventLastBlock(thor_block=24_000_000, block_dict={}), now=now)
    return {e.key: e.value for e in events}


def test_block_event_is_taken_from_data():
    import asyncio
    from jobs.achievement.extractor import AchievementsExtractor
    from jobs.fetch.cached.last_block import EventLastBlock
    ev = EventLastBlock(thor_block=24_000_000, block_dict={})
    events = asyncio.run(AchievementsExtractor(deps=None).extract_events_by_type(object(), ev))
    assert any(e.key == A.BLOCK_NUMBER and e.value == 24_000_000 for e in events)


def test_anniversary_only_soon_after_the_date():
    from datetime import datetime
    # THORChain was born on 2021-04-10 12:36 (local time of the birthday timestamp)
    assert _block_keys(datetime(2026, 4, 12, 12, 0).timestamp()) == {A.BLOCK_NUMBER: 24_000_000, A.ANNIVERSARY: 5}
    assert _block_keys(datetime(2026, 10, 1, 12, 0).timestamp()) == {A.BLOCK_NUMBER: 24_000_000}
    assert _block_keys(datetime(2026, 4, 9, 12, 0).timestamp()) == {A.BLOCK_NUMBER: 24_000_000}


# ---------- tracker: records are saved only once sent, stale metrics catch up silently ----------

import json

import pytest

from lib.date_utils import DAY
from tests.fakes import FakeDB

NOW = 1_790_000_000.0


@pytest.fixture
def tracker(monkeypatch):
    import jobs.achievement.tracker as tracker_mod
    monkeypatch.setattr(tracker_mod, 'now_ts', lambda: NOW)
    return AchievementsTracker(FakeDB(), stale_after=14 * DAY)


async def _put(tracker, **kw):
    await tracker.set_achievement_record(Achievement(A.DAU, **kw))


async def _stored(tracker):
    return await tracker.get_achievement_record(A.DAU, '')


@pytest.mark.asyncio
async def test_tracker_first_feed_only_records(tracker):
    assert await tracker.feed_data(Achievement(A.DAU, 1500)) is None
    rec = await _stored(tracker)
    assert (rec.value, rec.milestone, rec.last_seen_ts) == (1500, 1000, NOW)


@pytest.mark.asyncio
async def test_tracker_crossing_is_not_saved_until_sent(tracker):
    await _put(tracker, value=1500, milestone=1000, timestamp=NOW - 30 * DAY, last_seen_ts=NOW - DAY)

    ev = await tracker.feed_data(Achievement(A.DAU, 2100))
    assert (ev.value, ev.milestone, ev.prev_milestone, ev.timestamp) == (2100, 2000, 1000, NOW)
    # held back by the cooldown: nothing saved, so the next feed announces it again
    assert (await _stored(tracker)).value == 1500
    assert await tracker.feed_data(Achievement(A.DAU, 2100)) is not None

    await tracker.set_achievement_record(ev)
    assert await tracker.feed_data(Achievement(A.DAU, 2100)) is None


@pytest.mark.asyncio
async def test_tracker_stale_metric_catches_up_silently(tracker):
    await _put(tracker, value=1500, milestone=1000, timestamp=NOW - 300 * DAY, last_seen_ts=NOW - 20 * DAY)

    assert await tracker.feed_data(Achievement(A.DAU, 2100)) is None
    rec = await _stored(tracker)
    assert (rec.value, rec.milestone, rec.prev_milestone, rec.last_seen_ts) == (2100, 2000, 1000, NOW)


@pytest.mark.asyncio
async def test_tracker_record_from_before_last_seen_is_stale(tracker):
    # a record saved by the old code has no last_seen_ts at all
    old = Achievement(A.DAU, 1500, 1000, NOW - 300 * DAY)._asdict()
    del old['last_seen_ts']
    await tracker.db.redis.set(tracker.key(A.DAU), json.dumps(old))

    assert await tracker.feed_data(Achievement(A.DAU, 2100)) is None
    assert (await _stored(tracker)).milestone == 2000


@pytest.mark.asyncio
async def test_tracker_refreshes_last_seen_without_crossing(tracker):
    await _put(tracker, value=1500, milestone=1000, last_seen_ts=NOW - 2 * DAY)
    assert await tracker.feed_data(Achievement(A.DAU, 1600)) is None
    rec = await _stored(tracker)
    assert (rec.value, rec.last_seen_ts) == (1500, NOW)


@pytest.mark.asyncio
async def test_anniversary_is_announced_every_year(tracker, monkeypatch):
    from datetime import datetime
    import jobs.achievement.tracker as tracker_mod
    from jobs.achievement.extractor import AchievementsExtractor
    from jobs.fetch.cached.last_block import EventLastBlock

    async def feed_block(*date):
        """Feeds a block like the notifier does; returns the anniversary to announce, if any"""
        now = datetime(*date).timestamp()
        monkeypatch.setattr(tracker_mod, 'now_ts', lambda: now)
        announced = None
        for event in AchievementsExtractor.on_block(EventLastBlock(thor_block=24_000_000, block_dict={}), now=now):
            event = await tracker.feed_data(event)
            if event:
                await tracker.set_achievement_record(event)  # it is sent
                if event.key == A.ANNIVERSARY:
                    announced = event
        return announced

    # there is no record yet, but it is fed only within its window, so it is news
    ev = await feed_block(2026, 4, 11, 12)
    assert (ev.milestone, ev.prev_milestone) == (5, 0)
    assert await feed_block(2026, 4, 11, 13) is None  # once

    # the bot works all the year, but the anniversary is not fed outside its window...
    assert await feed_block(2026, 10, 1, 12) is None
    assert await feed_block(2027, 4, 9, 12) is None

    # ...so its record is a year old and far beyond stale_after: it must be announced, not saved silently
    ev = await feed_block(2027, 4, 11, 12)
    assert (ev.milestone, ev.prev_milestone) == (6, 5)
    assert await feed_block(2027, 4, 12, 12) is None

    # the bot was down for the whole window of the 7th one: no late congratulation
    assert await feed_block(2028, 4, 20, 12) is None
    assert await feed_block(2029, 4, 11, 12) is not None


@pytest.mark.asyncio
async def test_weekly_achievements_are_not_fed_in_preview():
    from types import SimpleNamespace
    from lib.logs import WithLogger
    from lib.run_context import run_context, RunMode
    from notify.pub_configure import PublicAlertJobExecutor

    fed = []

    async def on_data(sender, data):
        fed.append(data)

    executor = PublicAlertJobExecutor.__new__(PublicAlertJobExecutor)
    WithLogger.__init__(executor)
    executor.deps = SimpleNamespace(achievements=SimpleNamespace(on_data=on_data))

    with run_context(RunMode.PREVIEW):
        await executor._feed_achievements(None, 'weekly')
    with run_context(RunMode.TEST):
        await executor._feed_achievements(None, 'weekly')
    assert fed == []

    with run_context(RunMode.NORMAL):
        await executor._feed_achievements(None, 'weekly')
    assert fed == ['weekly']


# ---------- tracker: what the dashboard reads ----------

@pytest.mark.asyncio
async def test_tracker_marks_silent_catch_up(tracker):
    await _put(tracker, value=1500, milestone=1000, timestamp=NOW - 300 * DAY, last_seen_ts=NOW - 20 * DAY)
    await tracker.feed_data(Achievement(A.DAU, 2100))
    assert (await _stored(tracker)).silent

    # an announced one is not silent
    ev = await tracker.feed_data(Achievement(A.DAU, 5100))
    assert ev.milestone == 5000 and not ev.silent


@pytest.mark.asyncio
async def test_tracker_saves_live_value_even_below_threshold(tracker, monkeypatch):
    import jobs.achievement.tracker as tracker_mod

    assert await tracker.feed_data(Achievement(A.DAU, 250)) is None  # the cut-off is 300
    assert await _stored(tracker) is None
    assert await tracker.get_live_value(A.DAU) == {'value': 250, 'ts': NOW, 'peak': 250, 'peak_ts': NOW}

    # not rewritten on every feed
    await tracker.feed_data(Achievement(A.DAU, 260))
    assert (await tracker.get_live_value(A.DAU))['value'] == 250

    later = NOW + 2 * AchievementsTracker.LIVE_RESOLUTION
    monkeypatch.setattr(tracker_mod, 'now_ts', lambda: later)
    await tracker.feed_data(Achievement(A.DAU, 240))
    assert await tracker.get_live_value(A.DAU) == {'value': 240, 'ts': later, 'peak': 260, 'peak_ts': NOW}


@pytest.mark.asyncio
async def test_tracker_saves_a_record_event_at_once(tracker):
    # the largest swap of a batch will not be fed again, so its peak cannot wait for the next write
    await tracker.feed_data(Achievement(A.MAX_SWAP_AMOUNT_USD, 2_000_000))
    await tracker.feed_data(Achievement(A.MAX_SWAP_AMOUNT_USD, 9_000_000))
    await tracker.feed_data(Achievement(A.MAX_SWAP_AMOUNT_USD, 10_000))
    live = await tracker.get_live_value(A.MAX_SWAP_AMOUNT_USD)
    assert (live['value'], live['peak']) == (9_000_000, 9_000_000)


@pytest.mark.asyncio
async def test_tracker_live_peak_survives_restart(tracker):
    await tracker.feed_data(Achievement(A.COIN_MARKET_CAP_RANK, 30, descending=True))
    restarted = AchievementsTracker(tracker.db)
    await restarted.feed_data(Achievement(A.COIN_MARKET_CAP_RANK, 35, descending=True))
    live = await restarted.get_live_value(A.COIN_MARKET_CAP_RANK)
    assert (live['value'], live['peak']) == (35, 30)  # the best rank is the lowest


@pytest.mark.asyncio
async def test_anniversary_is_announced_every_year(monkeypatch):
    # fed only in the week after the date, its last feed is a year old every time: it must not be taken
    # for a metric that missed a milestone while the bot was down
    from datetime import datetime
    import jobs.achievement.tracker as tracker_mod
    from jobs.achievement.extractor import AchievementsExtractor
    from jobs.fetch.cached.last_block import EventLastBlock

    tracker = AchievementsTracker(FakeDB(), stale_after=14 * DAY)
    announced = []
    t, end = datetime(2026, 4, 1).timestamp(), datetime(2028, 4, 20).timestamp()
    while t < end:
        monkeypatch.setattr(tracker_mod, 'now_ts', lambda t=t: t)
        for ev in AchievementsExtractor.on_block(EventLastBlock(thor_block=24_000_000, block_dict={}), now=t):
            if ev.key == A.ANNIVERSARY and (r := await tracker.feed_data(ev)):
                await tracker.set_achievement_record(r)
                announced.append((datetime.fromtimestamp(t).date().isoformat(), r.value, r.prev_milestone))
        t += 3 * 3600

    # one post a year, on the day; always fresh, it is news even without a record to compare with
    assert announced == [('2026-04-10', 5, 0), ('2027-04-10', 6, 5), ('2028-04-10', 7, 6)]
