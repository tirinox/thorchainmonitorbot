"""
The achievements page: every milestone metric with its last milestone, its value now, the progress to the next
milestone and its cut-off parameters, plus a preview of the post.

The dashboard only reads what the bot's AchievementsTracker saves in Redis: the records (`Achievements:*`)
and the last fed values (`AchievementsLive`). build_row and make_preview_event are pure (data in, result out).
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from comm.localization.achievements.ach_eng import AchievementsEnglishLocalization
from comm.localization.achievements.common import AchievementsLocalizationBase
from dashboard.audit import AuditAction, LOCAL_ACTOR
from dashboard.context import DashboardContext
from jobs.achievement.ach_list import A, Achievement, ACHIEVEMENT_DESC_MAP, META_KEY_SPEC, SINGLE_EVENT_KEYS, \
    MILESTONES_EVERY_DIGIT, MILESTONES_EVERY_INT
from jobs.achievement.extractor import ANNIVERSARY_WINDOW
from jobs.achievement.notifier import AchievementsSettings
from jobs.achievement.tracker import AchievementsTracker
from lib.constants import THORCHAIN_BIRTHDAY
from lib.date_utils import now_ts, full_years_old_ts
from notify.alert_preview import AlertPreviewStore

RECORD_PREFIX = AchievementsTracker.key('')  # "Achievements:"
TEST_KEYS = {A.TEST, A.TEST_SPEC, A.TEST_DESCENDING}
# the direction is set by the feed; this is for a metric that has no record yet
DESCENDING_KEYS = {A.COIN_MARKET_CAP_RANK}

SAMPLE_VALUE = 1000  # for the preview of a metric nothing is known about


class AchStatus:
    NO_DATA = 'no_data'  # the bot has never fed this metric
    BELOW_THRESHOLD = 'below_threshold'  # under its cut-off: the tracker ignores it
    TRACKING = 'tracking'
    PENDING = 'pending'  # past the next milestone, the post is held back (cooldown) or was lost
    STALE = 'stale'  # not fed for longer than stale_after: its next milestone is saved without a post


class PreviewMode:
    LAST = 'last'  # the record as it is saved
    NEXT = 'next'  # the post of the next milestone
    VALUE = 'value'  # the post as if the metric had the given value

    ALL = (LAST, NEXT, VALUE)


def anniversary_ts(years: int) -> float:
    birth = datetime.fromtimestamp(THORCHAIN_BIRTHDAY)
    return birth.replace(year=birth.year + years).timestamp()


def scale_name(scale) -> str:
    if scale is MILESTONES_EVERY_INT:
        return 'every_int'
    if scale is MILESTONES_EVERY_DIGIT:
        return 'every_digit'
    return 'normal'


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def get_threshold(probe: Achievement) -> Optional[float]:
    """The cut-off of the metric; None if it has none (a per-pool metric has none without its pool)"""
    threshold = AchievementsTracker.get_threshold(probe)
    return threshold if isinstance(threshold, (int, float)) and threshold else None


def build_row(key: str, spec: str, record: Optional[Achievement], live: Optional[dict], now: float,
              stale_after: float, loc: AchievementsLocalizationBase) -> dict:
    desc = loc.get_achievement_description(key)
    descending = record.descending if record else key in DESCENDING_KEYS
    probe = Achievement(key, 0, specialization=spec, descending=descending)
    is_anniversary = key == A.ANNIVERSARY

    def fmt(v, short=True):
        if v is None:
            return None
        if key == A.COIN_MARKET_CAP_RANK:
            return f'#{int(v)}'
        return loc.format_value(v, probe, desc, short=short)

    def point(v, ts=None, **extra):
        return {'value': v, 'text': fmt(v), 'ts': ts or None, **extra}

    # ---- the value now
    current = None
    if is_anniversary:
        # it is fed only for a few days after the date, the calendar knows better
        years = full_years_old_ts(THORCHAIN_BIRTHDAY, now)
        current = {'value': years, 'ts': now, 'source': 'calendar'}
    elif live:
        if key in SINGLE_EVENT_KEYS:
            current = {'value': live.get('peak'), 'ts': live.get('peak_ts'), 'source': 'live'}
        else:
            current = {'value': live.get('value'), 'ts': live.get('ts'), 'source': 'live'}
    elif record:
        # a bot older than the live values: only the value at the milestone is known
        current = {'value': record.value, 'ts': record.timestamp or record.last_seen_ts, 'source': 'record'}
    if current and current['value'] is None:
        current = None
    value = current['value'] if current else None
    if current:
        current['text'] = fmt(value, short=False)

    # ---- the cut-off
    threshold = get_threshold(probe)
    meets_threshold = value is None or threshold is None or AchievementsTracker.meet_threshold(
        probe._replace(value=value))

    # ---- milestones and the progress between them
    next_value = (record.get_next_milestone() or None) if record else None
    next_ts = None
    progress = None
    if is_anniversary:
        next_value = value + 1
        last_ts, next_ts = anniversary_ts(value), anniversary_ts(value + 1)
        progress = _clamp01((now - last_ts) / (next_ts - last_ts))
    elif record and next_value is not None and value is not None:
        start = record.value if descending else record.milestone
        if next_value != start:
            progress = _clamp01((value - start) / (next_value - start))
    elif not record and threshold and value is not None and not descending:
        # not tracked yet: how far it is from its cut-off
        progress = _clamp01(value / threshold)

    # ---- status
    last_seen_ts = max(record.last_seen_ts if record else 0, (live or {}).get('ts') or 0)
    crossed = bool(record and value is not None and AchievementsTracker.is_crossed(record, probe._replace(value=value)))
    if is_anniversary:
        # outside of its window an anniversary is not fed, so it is not waiting for anything
        crossed = crossed and now - anniversary_ts(value) < ANNIVERSARY_WINDOW

    stale = bool(record and desc.catch_up_silently and now - record.last_seen_ts > stale_after)

    if not record and not live:
        status = AchStatus.NO_DATA
    elif not meets_threshold:
        status = AchStatus.BELOW_THRESHOLD
    elif not record:
        status = AchStatus.NO_DATA
    elif stale:
        status = AchStatus.STALE
    elif crossed:
        status = AchStatus.PENDING
    else:
        status = AchStatus.TRACKING

    title = desc.description.replace('\n', ' ')
    if META_KEY_SPEC in title:
        title = title.replace(META_KEY_SPEC, loc.pretty_specialization(probe) or 'per-pool')

    thresholds = ACHIEVEMENT_DESC_MAP[key].thresholds
    return {
        'id': AchievementsTracker.live_field(key, spec),
        'key': key,
        'specialization': spec,
        'title': title,
        'status': status,
        # the status may be another one (under the cut-off), these two are what the tracker will go by
        'stale': stale,
        'can_be_stale': desc.catch_up_silently,
        'crossed': crossed,
        'descending': descending,
        'single_event': key in SINGLE_EVENT_KEYS,
        'scale': scale_name(desc.milestone_scale),
        'threshold': point(threshold) if threshold else None,
        # a metric with a cut-off per pool, shown without its pool
        'threshold_count': len(thresholds) if isinstance(thresholds, dict) and not spec else None,
        # a record with no timestamp is the starting point: it was saved on the first feed without a post
        'milestone': point(record.value if descending else record.milestone, record.timestamp,
                           silent=record.silent, reached=fmt(record.value, short=False)) if record else None,
        'previous': point(record.prev_milestone, record.previous_ts) if record and record.has_previous else None,
        'current': current,
        'next': point(next_value, next_ts) if next_value is not None else None,
        'progress': progress,
        'last_seen_ts': last_seen_ts or None,
    }


def make_preview_event(key: str, spec: str, mode: str, value: Optional[int], record: Optional[Achievement],
                       current: Optional[int], now: float) -> Achievement:
    """The achievement the bot would announce: built the same way AchievementsTracker.feed_data builds it"""
    if key not in ACHIEVEMENT_DESC_MAP:
        raise ValueError(f'Unknown achievement {key!r}')
    if mode not in PreviewMode.ALL:
        raise ValueError(f'Unknown preview mode {mode!r}')

    if mode == PreviewMode.LAST:
        if not record:
            raise ValueError('Nothing is recorded for this achievement yet')
        return record

    descending = record.descending if record else key in DESCENDING_KEYS
    probe = Achievement(key, 0, specialization=spec, descending=descending)

    if mode == PreviewMode.VALUE:
        if not value or value <= 0:
            raise ValueError('The value must be positive')
        target = int(value)
    elif record:
        target = record.get_next_milestone()
        if not target:
            raise ValueError('There is no next milestone')
    else:
        # nothing recorded: take the milestone above what is known about the metric
        base = max(current or 0, get_threshold(probe) or 0) or SAMPLE_VALUE
        target = probe._replace(value=base).get_next_milestone() or base

    event = probe._replace(value=target)
    milestone = event.get_previous_milestone()
    previous = record
    if record and milestone == record.milestone:
        # the value has not left the recorded milestone: show that milestone again, with its own history
        previous = Achievement(key, 0, record.prev_milestone, record.previous_ts)
    return event._replace(
        milestone=milestone,
        timestamp=now,
        prev_milestone=previous.milestone if previous else 0,
        previous_ts=previous.timestamp if previous else 0,
    )


def _split_name(name: str) -> tuple[str, str]:
    key, _, spec = name.partition(':')
    return key, spec


async def _load_records(redis) -> dict[tuple[str, str], Achievement]:
    keys = sorted(await redis.keys(f'{RECORD_PREFIX}*'))
    values = await redis.mget(keys) if keys else []
    records = {}
    for redis_key, raw in zip(keys, values):
        try:
            records[_split_name(redis_key.removeprefix(RECORD_PREFIX))] = Achievement(**json.loads(raw))
        except (TypeError, ValueError):
            continue  # not a record or one from another version
    return records


async def _load_live(redis) -> dict[tuple[str, str], dict]:
    live = {}
    for field, raw in (await redis.hgetall(AchievementsTracker.LIVE_KEY) or {}).items():
        try:
            live[_split_name(field)] = json.loads(raw)
        except (TypeError, ValueError):
            continue
    return live


async def _cooldown_state(ctx: DashboardContext, settings: AchievementsSettings, now: float) -> dict:
    cd = settings.make_cooldown(ctx.deps.db)
    state = await cd.read(cd.event_name)
    started = state.time if isinstance(state.time, (int, float)) else 0
    active_until = started + settings.cooldown_period
    return {
        'period': settings.cooldown_period,
        'hits_before_cd': settings.hits_before_cd,
        'hits': state.count,  # posts since the last pause
        'active_until': active_until if started and active_until > now else None,
        'last_started_ts': started or None,
    }


async def list_achievements(ctx: DashboardContext) -> dict:
    redis = ctx.deps.db.redis
    now = now_ts()
    settings = ctx.achievement_settings
    records, live, cooldown = await asyncio.gather(
        _load_records(redis), _load_live(redis), _cooldown_state(ctx, settings, now))

    loc = AchievementsEnglishLocalization()
    items = []
    for key in ACHIEVEMENT_DESC_MAP:
        if key in TEST_KEYS:
            continue
        # one row per pool (or whatever the metric is split by), or a single row
        specs = sorted({spec for k, spec in [*records, *live] if k == key}) or ['']
        for spec in specs:
            items.append(build_row(key, spec, records.get((key, spec)), live.get((key, spec)), now,
                                   settings.stale_after, loc))

    return {
        'now': now,
        'settings': {
            'enabled': settings.enabled,
            'stale_after': settings.stale_after,
            'anniversary_window': ANNIVERSARY_WINDOW,
            'cooldown': cooldown,
        },
        'items': items,
    }


async def set_stale(ctx: DashboardContext, key: str, specialization: str, stale: bool,
                    actor: str = LOCAL_ACTOR) -> dict:
    """
    Makes the tracker take the metric for stale (its next milestone is saved without a post) or for fresh
    (its next milestone is posted). The tracker tells one from the other by the record's last_seen_ts.
    A feed that crosses no milestone makes a stale metric fresh again by itself.
    """
    if key not in ACHIEVEMENT_DESC_MAP:
        raise ValueError(f'Unknown achievement {key!r}')
    if not ACHIEVEMENT_DESC_MAP[key].catch_up_silently:
        raise ValueError(f'{key!r} is never caught up silently, so it cannot be stale')

    tracker = AchievementsTracker(ctx.deps.db)
    record = await tracker.get_achievement_record(key, specialization)
    if not record:
        raise ValueError('Nothing is recorded for this achievement yet')

    last_seen_ts = 0 if stale else now_ts()
    await tracker.set_achievement_record(record._replace(last_seen_ts=last_seen_ts))
    await ctx.audit.record(
        AuditAction.ACHIEVEMENT_STALE if stale else AuditAction.ACHIEVEMENT_FRESH, actor,
        AchievementsTracker.live_field(key, specialization),
        old_last_seen_ts=record.last_seen_ts, new_last_seen_ts=last_seen_ts,
    )
    return {'ok': True, 'stale': stale, 'last_seen_ts': last_seen_ts}


async def preview_achievement(ctx: DashboardContext, key: str, specialization: str = '',
                              mode: str = PreviewMode.NEXT, value: Optional[int] = None) -> dict:
    """
    Builds the post of an achievement for every public channel, the way a preview run of a job does:
    the messages are captured instead of being sent and kept for an hour (see GET /previews/{run_id}).
    Nothing is saved to the achievement records.
    """
    d = ctx.deps
    tracker = AchievementsTracker(d.db)
    record, live = await asyncio.gather(
        tracker.get_achievement_record(key, specialization),
        tracker.get_live_value(key, specialization),
    )

    current = (live or {}).get('peak' if key in SINGLE_EVENT_KEYS else 'value')
    event = make_preview_event(key, specialization, mode, value, record, current, now_ts())

    with d.broadcaster.capture() as captured:
        await d.alert_presenter.handle_data(event)
    if not captured:
        raise RuntimeError('The achievement produced no messages: are there any broadcasting.channels?')

    preview = await AlertPreviewStore(d.db).save(f'ach-{uuid.uuid4().hex[:12]}', captured)
    return {**preview, 'event': event._asdict()}
