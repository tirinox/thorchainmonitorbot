from types import SimpleNamespace

import pytest

from comm.localization.achievements.ach_eng import AchievementsEnglishLocalization
from dashboard.audit import AuditLog
from dashboard.services import achievements as svc
from dashboard.services.achievements import AchStatus, PreviewMode, build_row, make_preview_event
from jobs.achievement.ach_list import A, Achievement
from jobs.achievement.notifier import AchievementsSettings
from jobs.achievement.tracker import AchievementsTracker
from lib.config import Config
from lib.cooldown import CooldownRecord
from lib.constants import THORCHAIN_BIRTHDAY
from lib.date_utils import DAY, HOUR
from notify.broadcast import CapturedMessage
from notify.channel import ChannelDescriptor, BoardMessage
from tests.fakes import FakeDB, FakePubSubRedis

NOW = 1_790_000_000.0
STALE_AFTER = 14 * DAY
LOC = AchievementsEnglishLocalization()


def row(key, record=None, live=None, spec='', now=NOW):
    return build_row(key, spec, record, live, now, STALE_AFTER, LOC)


def live_value(value, peak=None, ts=NOW - 60):
    return {'value': value, 'ts': ts, 'peak': peak or value, 'peak_ts': ts}


# ---------- rows ----------

def test_row_tracking_shows_progress_between_milestones():
    record = Achievement(A.DAU, 2100, 2000, NOW - 10 * DAY, 1000, NOW - 40 * DAY, last_seen_ts=NOW - HOUR)
    r = row(A.DAU, record, live_value(3500))

    assert r['status'] == AchStatus.TRACKING
    assert (r['milestone']['text'], r['milestone']['ts'], r['milestone']['reached']) == ('2K', NOW - 10 * DAY, '2,100')
    assert (r['previous']['text'], r['previous']['ts']) == ('1K', NOW - 40 * DAY)
    assert (r['current']['text'], r['current']['source']) == ('3,500', 'live')
    assert (r['next']['value'], r['next']['text']) == (5000, '5K')
    assert r['progress'] == pytest.approx(0.5)
    assert r['threshold']['value'] == 300
    assert r['scale'] == 'normal'


def test_row_without_data():
    r = row(A.SWAP_COUNT_TOTAL)
    assert r['status'] == AchStatus.NO_DATA
    assert r['milestone'] is None and r['current'] is None and r['next'] is None and r['progress'] is None
    assert r['threshold'] is None  # no cut-off at all


def test_row_below_threshold_shows_the_way_to_the_cut_off():
    r = row(A.MAU, live=live_value(1300))
    assert r['status'] == AchStatus.BELOW_THRESHOLD
    assert r['progress'] == pytest.approx(1300 / 6500)
    assert r['next'] is None


def test_row_fallen_below_its_milestone_has_no_progress():
    record = Achievement(A.DAU, 2100, 2000, NOW - DAY, last_seen_ts=NOW - HOUR)
    assert row(A.DAU, record, live_value(900))['progress'] == 0.0
    # and under the cut-off the tracker does not even look at it
    assert row(A.DAU, record, live_value(200))['status'] == AchStatus.BELOW_THRESHOLD


def test_row_pending_when_the_value_is_past_the_next_milestone():
    record = Achievement(A.DAU, 2100, 2000, NOW - DAY, last_seen_ts=NOW - HOUR)
    r = row(A.DAU, record, live_value(5200))
    assert (r['status'], r['progress']) == (AchStatus.PENDING, 1.0)


def test_row_stale_and_silent():
    record = Achievement(A.DAU, 2100, 2000, NOW - 20 * DAY, last_seen_ts=NOW - 20 * DAY, silent=True)
    r = row(A.DAU, record)
    assert r['status'] == AchStatus.STALE
    assert r['milestone']['silent']
    # a bot that does not save live values yet: only the value at the milestone is known
    assert (r['current']['value'], r['current']['source']) == (2100, 'record')


def test_row_of_a_record_event_uses_its_peak():
    record = Achievement(A.MAX_SWAP_AMOUNT_USD, 21_300_000, 20_000_000, NOW - DAY, last_seen_ts=NOW - HOUR)
    r = row(A.MAX_SWAP_AMOUNT_USD, record, live_value(12_000, peak=35_000_000))
    assert r['single_event']
    assert r['current']['value'] == 35_000_000
    assert r['progress'] == pytest.approx(0.5)  # $20M => $50M


def test_row_rank_goes_down():
    record = Achievement(A.COIN_MARKET_CAP_RANK, 30, 31, NOW - DAY, descending=True, last_seen_ts=NOW - HOUR)
    r = row(A.COIN_MARKET_CAP_RANK, record, live_value(30))
    assert r['descending']
    assert (r['milestone']['text'], r['current']['text'], r['next']['text']) == ('#30', '#30', '#29')
    assert r['progress'] == 0.0
    assert r['scale'] == 'every_int'

    assert row(A.COIN_MARKET_CAP_RANK, record, live_value(50))['status'] == AchStatus.BELOW_THRESHOLD  # under top 42


def test_row_anniversary_counts_by_the_calendar():
    half_past_five = THORCHAIN_BIRTHDAY + 5.5 * 365.25 * DAY
    r = row(A.ANNIVERSARY, now=half_past_five)
    assert (r['current']['value'], r['next']['value']) == (5, 6)
    assert r['progress'] == pytest.approx(0.5, abs=0.01)
    assert r['next']['ts'] > half_past_five

    # the date has passed long ago and nobody feeds it any more: nothing is waiting to be posted
    record = Achievement(A.ANNIVERSARY, 4, 4, half_past_five - 500 * DAY, last_seen_ts=half_past_five - HOUR)
    assert row(A.ANNIVERSARY, record, now=half_past_five)['status'] == AchStatus.TRACKING


def test_row_per_pool(per_pool_key):
    generic = row(per_pool_key)
    assert generic['title'] == 'Largest per-pool liquidity add'
    assert generic['threshold'] is None and generic['threshold_count'] == 3

    btc = row(per_pool_key, spec='BTC.BTC', live=live_value(9_000_000))
    assert btc['id'] == f'{per_pool_key}:BTC.BTC'
    assert btc['title'] == 'Largest BTC liquidity add'
    assert (btc['threshold']['value'], btc['threshold_count']) == (8143923, None)


# ---------- preview events ----------

def test_preview_event_of_the_next_milestone_is_built_like_the_tracker_does():
    record = Achievement(A.DAU, 2100, 2000, NOW - 10 * DAY, 1000, NOW - 40 * DAY)
    ev = make_preview_event(A.DAU, '', PreviewMode.NEXT, None, record, 3500, NOW)
    assert ev == Achievement(A.DAU, 5000, 5000, NOW, 2000, NOW - 10 * DAY)

    assert make_preview_event(A.DAU, '', PreviewMode.LAST, None, record, 3500, NOW) is record


def test_preview_event_with_a_custom_value():
    record = Achievement(A.DAU, 2100, 2000, NOW - 10 * DAY, 1000, NOW - 40 * DAY)
    ev = make_preview_event(A.DAU, '', PreviewMode.VALUE, 12_345, record, None, NOW)
    assert (ev.value, ev.milestone, ev.prev_milestone, ev.previous_ts) == (12_345, 10_000, 2000, NOW - 10 * DAY)

    # still at the recorded milestone: that milestone again, not "previous: itself"
    ev = make_preview_event(A.DAU, '', PreviewMode.VALUE, 2500, record, None, NOW)
    assert (ev.milestone, ev.prev_milestone, ev.previous_ts) == (2000, 1000, NOW - 40 * DAY)


def test_preview_event_without_a_record():
    # above what is known: the live value, else the cut-off, else a sample
    assert make_preview_event(A.MAU, '', PreviewMode.NEXT, None, None, 1300, NOW).milestone == 10_000
    assert make_preview_event(A.MAU, '', PreviewMode.NEXT, None, None, 30_000, NOW).milestone == 50_000
    assert make_preview_event(A.SWAP_COUNT_TOTAL, '', PreviewMode.NEXT, None, None, None, NOW).milestone == 2000

    rank = make_preview_event(A.COIN_MARKET_CAP_RANK, '', PreviewMode.NEXT, None, None, None, NOW)
    assert rank.descending and rank.value == 41


def test_preview_event_errors():
    with pytest.raises(ValueError):
        make_preview_event('nope', '', PreviewMode.NEXT, None, None, None, NOW)
    with pytest.raises(ValueError):
        make_preview_event(A.DAU, '', PreviewMode.LAST, None, None, None, NOW)
    with pytest.raises(ValueError):
        make_preview_event(A.DAU, '', PreviewMode.VALUE, None, None, None, NOW)
    with pytest.raises(ValueError):
        make_preview_event(A.DAU, '', 'other', None, None, None, NOW)


# ---------- service ----------

SETTINGS = AchievementsSettings(enabled=True, stale_after=STALE_AFTER, cooldown_period=900.0, hits_before_cd=5)


def make_ctx(db, **deps):
    return SimpleNamespace(deps=SimpleNamespace(db=db, **deps), achievement_settings=SETTINGS)


def test_settings_are_read_from_the_config():
    cfg = Config(data={'achievements': {'enabled': False, 'stale_after': '3d',
                                        'cooldown': {'period': '15m', 'hits_before_cd': 5}}})
    assert AchievementsSettings.load(cfg) == AchievementsSettings(False, 3 * DAY, 900.0, 5)
    assert AchievementsSettings.load(Config(data={})) == AchievementsSettings(True, 14 * DAY, 600.0, 3)


@pytest.mark.asyncio
async def test_list_achievements(monkeypatch, per_pool_key):
    monkeypatch.setattr(svc, 'now_ts', lambda: NOW)
    db = FakeDB()
    tracker = AchievementsTracker(db)
    await tracker.feed_data(Achievement(A.DAU, 1500))
    await tracker.feed_data(Achievement(A.MAU, 3000))
    await tracker.feed_data(Achievement(A.TEST, 77))
    await tracker.set_achievement_record(Achievement(per_pool_key, 9_000_000, 5_000_000,
                                                     specialization='BTC.BTC'))
    await db.redis.set('Achievements:garbage', 'not json')

    await SETTINGS.make_cooldown(db).write(SETTINGS.COOLDOWN_NAME, CooldownRecord(NOW - 60, 2))

    result = await svc.list_achievements(make_ctx(db))

    assert result['settings'] == {
        'enabled': True,
        'stale_after': STALE_AFTER,
        'anniversary_window': 7 * DAY,
        'cooldown': {'period': 900.0, 'hits_before_cd': 5, 'hits': 2, 'active_until': NOW + 840,
                     'last_started_ts': NOW - 60},
    }

    rows = {r['id']: r for r in result['items']}
    assert not any(key.startswith('__test') for key in rows)
    assert rows['dau']['status'] == AchStatus.TRACKING
    assert rows['mau']['status'] == AchStatus.BELOW_THRESHOLD
    assert rows['tvl']['status'] == AchStatus.NO_DATA
    # a per-pool metric is listed by the pools it has data for
    assert f'{per_pool_key}:BTC.BTC' in rows and per_pool_key not in rows


@pytest.mark.asyncio
async def test_preview_captures_the_post_and_saves_nothing(monkeypatch):
    monkeypatch.setattr(svc, 'now_ts', lambda: NOW)
    db = FakeDB()
    channel = ChannelDescriptor('telegram', '@chan', 'eng')
    handled = []

    class FakeBroadcaster:
        def capture(self):
            from contextlib import contextmanager

            @contextmanager
            def cm():
                self.captured = []
                yield self.captured

            return cm()

    broadcaster = FakeBroadcaster()

    async def handle_data(event):
        handled.append(event)
        text = LOC.notification_achievement_unlocked(event)
        broadcaster.captured.append(CapturedMessage(channel, BoardMessage(text, msg_type='public:achievement')))

    ctx = make_ctx(db, broadcaster=broadcaster, alert_presenter=SimpleNamespace(handle_data=handle_data))
    await AchievementsTracker(db).set_achievement_record(Achievement(A.DAU, 2100, 2000, NOW - DAY))
    keys_before = set(await db.redis.keys('Achievements*'))

    preview = await svc.preview_achievement(ctx, A.DAU)

    assert handled == [Achievement(A.DAU, 5000, 5000, NOW, 2000, NOW - DAY)]
    assert preview['event']['milestone'] == 5000
    assert preview['run_id'].startswith('ach-')
    [message] = preview['messages']
    assert message['channel']['selector'] == channel.short_coded
    assert '5K' in message['text'] and message['image'] is None
    assert set(await db.redis.keys('Achievements*')) == keys_before

    with pytest.raises(ValueError):
        await svc.preview_achievement(ctx, 'nope')


# ---- stale on demand ----

@pytest.mark.asyncio
async def test_set_stale_decides_whether_the_next_milestone_is_posted(monkeypatch):
    import jobs.achievement.tracker as tracker_mod
    monkeypatch.setattr(svc, 'now_ts', lambda: NOW)
    monkeypatch.setattr(tracker_mod, 'now_ts', lambda: NOW)
    db = FakeDB(FakePubSubRedis())
    ctx = make_ctx(db)
    ctx.audit = AuditLog(db)
    tracker = AchievementsTracker(db, STALE_AFTER)
    # not fed for a long time: the tracker would save the milestone it missed without a post
    await tracker.set_achievement_record(Achievement(A.DAU, 2100, 2000, NOW - 90 * DAY, last_seen_ts=NOW - 60 * DAY))

    assert (await svc.list_achievements(ctx))['items'][0]['stale']
    await svc.set_stale(ctx, A.DAU, '', False, actor='alice')
    row = (await svc.list_achievements(ctx))['items'][0]
    assert (row['id'], row['stale'], row['status']) == ('dau', False, AchStatus.TRACKING)
    assert await tracker.feed_data(Achievement(A.DAU, 5100)) is not None  # to be posted

    await svc.set_stale(ctx, A.DAU, '', True, actor='alice')
    assert (await svc.list_achievements(ctx))['items'][0]['status'] == AchStatus.STALE
    assert await tracker.feed_data(Achievement(A.DAU, 5100)) is None  # saved without a post
    record = await tracker.get_achievement_record(A.DAU, '')
    assert (record.milestone, record.silent) == (5000, True)

    entries = (await ctx.audit.list())['items']
    assert [(e['action'], e['actor'], e['target']) for e in entries] == [
        ('achievement.stale', 'alice', 'dau'), ('achievement.fresh', 'alice', 'dau')]
    assert entries[1]['details'] == {'old_last_seen_ts': NOW - 60 * DAY, 'new_last_seen_ts': NOW}

    with pytest.raises(ValueError):
        await svc.set_stale(ctx, A.MAU, '', True)  # no record
    with pytest.raises(ValueError):
        await svc.set_stale(ctx, 'nope', '', True)
