"""
Human-readable schedules and run-time previews for scheduler jobs.

Triggers are built with APScheduler itself, so descriptions and "next runs" follow exactly the rules the bot
uses — including its quirk that cron fields below the most significant one you set default to their minimum
(hour=9 means 09:00:00, not every minute of hour 9).
"""
import re
from datetime import datetime, timezone as dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from tzlocal import get_localzone

from models.sched import SchedVariant, SchedJobCfg
from notify.pub_scheduler import PublicScheduler

UTC_ALIASES = {'Etc/UTC', 'UTC', 'Etc/Universal', 'Universal', 'Etc/Zulu', 'Zulu', 'Etc/GMT', 'GMT'}
MAX_FIXED_TIMES = 6  # "at 09:00, 12:00 and 18:00" reads fine; longer lists do not

DOW_NAMES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']  # APScheduler: 0 = Monday
DOW_TITLES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
DOW_PLURAL = ['Mondays', 'Tuesdays', 'Wednesdays', 'Thursdays', 'Fridays', 'Saturdays', 'Sundays']
MONTH_NAMES = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
MONTH_TITLES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
                'October', 'November', 'December']


# ---------- timezones ----------

def normalize_tz_name(name: str) -> str:
    return 'UTC' if name in UTC_ALIASES else name


def parse_tz(name: Optional[str]) -> Optional[ZoneInfo]:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


async def get_scheduler_timezone(db) -> str:
    """The timezone the bot's scheduler uses (the bot stores it on start); falls back to this machine's."""
    stored = None
    if db and db.redis is not None:
        stored = await db.redis.get(PublicScheduler.DB_KEY_TIMEZONE)
    name = stored if stored and parse_tz(stored) else str(get_localzone())
    return normalize_tz_name(name)


# ---------- triggers and next runs ----------

def build_trigger(variant: str, interval: Optional[dict], cron: Optional[dict], date: Optional[dict], tz: str):
    """Raises ValueError (or pydantic's ValidationError, also a ValueError) for an invalid schedule."""
    if variant == SchedVariant.INTERVAL:
        params = {k: v for k, v in (interval or {}).items() if v}
        if not params:
            raise ValueError('Interval needs at least one non-zero field')
        return IntervalTrigger(**params, timezone=tz)
    if variant == SchedVariant.CRON:
        params = {k: v for k, v in (cron or {}).items() if v not in (None, '')}
        return CronTrigger(**params, timezone=tz)
    if variant == SchedVariant.DATE:
        run_date = (date or {}).get('run_date')
        if not run_date:
            raise ValueError('Pick a run date')
        return DateTrigger(run_date=run_date, timezone=tz)
    raise ValueError(f'Unknown schedule variant: {variant!r}')


def trigger_for_job(job: SchedJobCfg, tz: str):
    return build_trigger(
        job.variant,
        job.interval.model_dump() if job.interval else None,
        job.cron.model_dump() if job.cron else None,
        job.date.model_dump() if job.date else None,
        tz,
    )


def next_fire_times(trigger, count: int = 5, now: Optional[datetime] = None) -> list[datetime]:
    now = now or datetime.now(dt_timezone.utc)
    times, previous = [], None
    for _ in range(count):
        fire = trigger.get_next_fire_time(previous, now)
        if fire is None or (times and fire <= times[-1]):
            break
        times.append(fire)
        previous = now = fire
    return times


# ---------- descriptions ----------

def _plural(n: int, unit: str) -> str:
    return f'{n} {unit}' if n == 1 else f'{n} {unit}s'


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _ordinal(n: int) -> str:
    suffix = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'


def describe_interval(interval: dict) -> str:
    parts = [(interval.get(unit) or 0, unit.rstrip('s')) for unit in ('weeks', 'days', 'hours', 'minutes', 'seconds')]
    parts = [(n, unit) for n, unit in parts if n]
    if len(parts) == 1 and parts[0][0] == 1:
        return f'Every {parts[0][1]}'
    return 'Every ' + ' '.join(_plural(n, unit) for n, unit in parts)


_STEP = re.compile(r'^\*/(\d+)$')
_RANGE = re.compile(r'^(\d+)-(\d+)$')


def _step(expr: str) -> Optional[int]:
    m = _STEP.match(expr)
    return int(m.group(1)) if m else None


def _numbers(expr: str, max_items=24) -> Optional[list[int]]:
    """'9', '9,18' or '9-17' -> [..]; None for anything else (steps, names, 'last'...)."""
    values = []
    for part in expr.split(','):
        if part.isdigit():
            values.append(int(part))
        elif m := _RANGE.match(part):
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi < lo or hi - lo > max_items:
                return None
            values.extend(range(lo, hi + 1))
        else:
            return None
    return sorted(set(values))


def _hour_scope(hour: str) -> Optional[str]:
    """'' for every hour, a phrase limiting the hours, or None if we cannot describe it."""
    if hour == '*':
        return ''
    if m := _RANGE.match(hour):
        return f'between {int(m.group(1)):02d}:00 and {int(m.group(2)):02d}:59'
    if (n := _step(hour)) is not None:
        return f'during every {_ordinal(n)} hour' if n > 1 else ''
    hours = _numbers(hour)
    if hours is None:
        return None
    if len(hours) == 1:
        return f'between {hours[0]:02d}:00 and {hours[0]:02d}:59'
    return f"during hours {_join([str(h) for h in hours])}"


def _minute_scope(minute: str) -> Optional[str]:
    """'' for every minute, a phrase limiting the minutes, or None if we cannot describe it."""
    if minute == '*':
        return ''
    if m := _RANGE.match(minute):
        return f'during minutes {m.group(1)}–{m.group(2)}'
    if (n := _step(minute)) is not None:
        return f'during every {_ordinal(n)} minute' if n > 1 else ''
    minutes = _numbers(minute, max_items=60)
    if minutes is None:
        return None
    return f"during minute{'s' if len(minutes) > 1 else ''} {_join([f':{m:02d}' for m in minutes])}"


def _describe_subminute(second: str, minute: str, hour: str) -> str:
    """Schedules firing more than once a minute (second is '*', a step, a list or a range)."""
    fallback = f'At second {second}, minute {minute}, hour {hour}'
    if second == '*':
        base = 'Every second'
    elif (n := _step(second)) is not None:
        base = 'Every second' if n == 1 else f'Every {n} seconds'
    elif (seconds := _numbers(second, max_items=60)) is not None:
        base = f"Every minute at second{'s' if len(seconds) > 1 else ''} {_join([str(x) for x in seconds])}"
    else:
        return fallback

    minute_scope, hour_scope = _minute_scope(minute), _hour_scope(hour)
    if minute_scope is None or hour_scope is None:
        return fallback
    text = base
    if minute_scope:
        text += f' {minute_scope}'
        text += f', {hour_scope}' if hour_scope else ' of every hour'
    elif hour_scope:
        text += f' {hour_scope}'
    return text


def _describe_time(second: str, minute: str, hour: str) -> tuple[str, Optional[list[str]]]:
    """Returns (text, fixed times like ['09:00'] or None)."""
    if not second.isdigit():
        return _describe_subminute(second, minute, hour), None

    sec = int(second)
    sec_suffix = f':{sec:02d}' if sec else ''
    hours = _numbers(hour)
    hour_range = _RANGE.match(hour)

    if minute == '*':
        base = f'Every minute at second {sec}' if sec else 'Every minute'
    elif (n := _step(minute)) is not None:
        base = 'Every minute' if n == 1 else f'Every {n} minutes'
    else:
        minutes = _numbers(minute, max_items=60)
        if minutes is None:
            return f'At second {second}, minute {minute}, hour {hour}', None
        at_minutes = _join([f':{m:02d}{sec_suffix}' for m in minutes])
        if hour == '*':
            return ('Every hour' if minutes == [0] and not sec else f'Every hour at {at_minutes}'), None
        if (n := _step(hour)) is not None:
            return f'Every {n} hours at {at_minutes}', None
        if hours is None:
            return f'At minute {minute} of hour {hour}', None
        times = [f'{h:02d}:{m:02d}{sec_suffix}' for h in hours for m in minutes]
        if len(times) <= MAX_FIXED_TIMES:
            return f'At {_join(times)}', times
        if hour_range and len(minutes) == 1:
            lo, hi = int(hour_range.group(1)), int(hour_range.group(2))
            return f'Every hour at {at_minutes} from {lo:02d}:{minutes[0]:02d} to {hi:02d}:{minutes[0]:02d}', None
        return f'At {at_minutes} during hours {hour}', None

    # every minute / every N minutes, possibly limited to some hours
    scope = _hour_scope(hour)
    if scope is None:
        return f'{base} (hours {hour})', None
    return (f'{base} {scope}' if scope else base), None


def _dow_index(token: str) -> Optional[int]:
    token = token.strip().lower()
    if token.isdigit() and int(token) < 7:
        return int(token)
    return DOW_NAMES.index(token) if token in DOW_NAMES else None


def _describe_dow(expr: str) -> str:
    normalized = expr.lower().replace(' ', '')
    if normalized in ('mon-fri', '0-4'):
        return 'on weekdays'
    if normalized in ('sat,sun', 'sat-sun', '5,6', '5-6', 'sun,sat'):
        return 'on weekends'
    parts = []
    for token in normalized.split(','):
        if '-' in token:
            lo, hi = (_dow_index(t) for t in token.split('-', 1))
            if lo is None or hi is None:
                return f'on day_of_week {expr}'
            parts.append(f'{DOW_TITLES[lo]}–{DOW_TITLES[hi]}')
        else:
            i = _dow_index(token)
            if i is None:
                return f'on day_of_week {expr}'
            parts.append(DOW_TITLES[i])
    if len(parts) == 1 and '–' not in parts[0]:
        return f'on {DOW_PLURAL[DOW_TITLES.index(parts[0])]}'
    return f'on {_join(parts)}'


def _describe_day(expr: str) -> str:
    if expr == 'last':
        return 'on the last day of the month'
    if (n := _step(expr)) is not None:
        return f'every {n} days of the month'
    if m := _RANGE.match(expr):
        return f'on days {m.group(1)}–{m.group(2)} of the month'
    days = _numbers(expr, max_items=31)
    if days is not None:
        return f'on the {_join([_ordinal(d) for d in days])} of the month'
    return f'on day {expr}'


def _month_title(token: str) -> Optional[str]:
    token = token.strip().lower()
    if token.isdigit() and 1 <= int(token) <= 12:
        return MONTH_TITLES[int(token) - 1]
    return MONTH_TITLES[MONTH_NAMES.index(token)] if token in MONTH_NAMES else None


def _describe_month(expr: str) -> str:
    if (n := _step(expr)) is not None:
        return f'every {n} months'
    names = [_month_title(t) for t in expr.split(',')]
    if all(names):
        return f'in {_join(names)}'
    return f'in months {expr}'


def cron_fields(cron: dict, tz: str = 'UTC') -> dict[str, str]:
    """The effective expressions APScheduler will use (omitted lesser fields become their minimum)."""
    trigger = build_trigger(SchedVariant.CRON, None, cron, None, tz)
    return {f.name: str(f) for f in trigger.fields}


def describe_cron(cron: dict, tz: str = 'UTC') -> tuple[str, Optional[list[str]]]:
    f = cron_fields(cron, tz)
    text, times = _describe_time(f['second'], f['minute'], f['hour'])

    qualifiers = []
    if f['day_of_week'] != '*':
        qualifiers.append(_describe_dow(f['day_of_week']))
    if f['day'] != '*':
        qualifiers.append(_describe_day(f['day']))
    if f['month'] != '*':
        qualifiers.append(_describe_month(f['month']))
    if f['week'] != '*':
        qualifiers.append(f"in ISO week {f['week']}")
    if f['year'] != '*':
        qualifiers.append(f"in {f['year']}")

    if qualifiers:
        text = f"{text}, {', '.join(qualifiers)}"
    elif times:
        text = f'{text} every day'
    return text, times


def describe_schedule(variant: str, interval: Optional[dict], cron: Optional[dict], date: Optional[dict],
                      tz: str) -> dict:
    """
    {'text': ..., 'times': fixed daily times in the scheduler timezone or None, 'run_ts': for one-off jobs,
     'tz_relevant': whether the timezone changes when it fires ("every 10 minutes" does not care)}
    """
    if variant == SchedVariant.INTERVAL:
        return {'text': describe_interval(interval or {}), 'times': None, 'run_ts': None, 'tz_relevant': False}
    if variant == SchedVariant.CRON:
        text, times = describe_cron(cron or {}, tz)
        fields = cron_fields(cron or {}, tz)
        tz_relevant = any(fields[f] != '*' for f in ('hour', 'day', 'day_of_week', 'month', 'week', 'year'))
        return {'text': text, 'times': times, 'run_ts': None, 'tz_relevant': tz_relevant}
    if variant == SchedVariant.DATE:
        trigger = build_trigger(variant, None, None, date, tz)
        run_at = trigger.run_date
        return {'text': f"Once, on {run_at.strftime('%-d %b %Y at %H:%M')}", 'times': None,
                'run_ts': run_at.timestamp(), 'tz_relevant': True}
    return {'text': '', 'times': None, 'run_ts': None, 'tz_relevant': False}


def convert_times(times: list[str], from_tz: str, to_tz: str, on_date=None) -> Optional[list[dict]]:
    """
    Daily times like '09:00' in the scheduler timezone → the viewer's timezone, as
    [{'time': '12:00', 'day_shift': 0}, ...]. None when both zones have the same offset today.
    """
    src, dst = parse_tz(from_tz), parse_tz(to_tz)
    if not times or src is None or dst is None:
        return None
    on_date = on_date or datetime.now(src).date()
    probe = datetime.combine(on_date, datetime.min.time(), tzinfo=src)
    if probe.utcoffset() == probe.astimezone(dst).utcoffset():
        return None

    result = []
    for t in times:
        parts = [int(p) for p in t.split(':')]
        local = datetime(on_date.year, on_date.month, on_date.day, *parts, tzinfo=src).astimezone(dst)
        fmt = '%H:%M:%S' if len(parts) == 3 else '%H:%M'
        result.append({'time': local.strftime(fmt), 'day_shift': (local.date() - on_date).days})
    return result


def schedule_info(variant, interval, cron, date, scheduler_tz: str, viewer_tz: Optional[str] = None) -> dict:
    info = describe_schedule(variant, interval, cron, date, scheduler_tz)
    info['timezone'] = scheduler_tz
    info['local_times'] = convert_times(info['times'], scheduler_tz, viewer_tz) if viewer_tz else None
    return info


def job_schedule_info(job: SchedJobCfg, scheduler_tz: str, viewer_tz: Optional[str] = None) -> dict:
    try:
        return schedule_info(
            job.variant,
            job.interval.model_dump() if job.interval else None,
            job.cron.model_dump() if job.cron else None,
            job.date.model_dump() if job.date else None,
            scheduler_tz, viewer_tz,
        )
    except ValueError as e:
        # a job saved before validation existed; the bot cannot schedule it either
        return {'text': f'Invalid schedule: {e}', 'times': None, 'run_ts': None, 'timezone': scheduler_tz,
                'local_times': None, 'invalid': True}


def preview_schedule(variant, interval, cron, date, scheduler_tz: str, viewer_tz: Optional[str] = None,
                     count: int = 5, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(dt_timezone.utc)
    try:
        info = schedule_info(variant, interval, cron, date, scheduler_tz, viewer_tz)
        trigger = build_trigger(variant, interval, cron, date, scheduler_tz)
    except ValueError as e:
        return {'ok': False, 'error': _clean_error(e), 'timezone': scheduler_tz}

    runs = next_fire_times(trigger, count, now)
    warning = None
    if variant == SchedVariant.DATE and runs and runs[0] < now:
        warning = 'This time is in the past: the job would never run.'
    elif not runs:
        warning = 'This schedule never fires.'
    elif variant == SchedVariant.INTERVAL:
        warning = 'Interval runs are counted from the moment the config is applied.'
    return {
        'ok': True,
        'error': None,
        'warning': warning,
        'timezone': scheduler_tz,
        'schedule': info,
        'next_runs': [r.timestamp() for r in runs],
    }


def _clean_error(e: Exception) -> str:
    errors = getattr(e, 'errors', None)
    if callable(errors):  # pydantic ValidationError
        return '; '.join(err.get('msg', '') for err in errors())
    return str(e)


def validate_job_schedule(job: SchedJobCfg, tz: str):
    """Raises ValueError with a readable message if APScheduler would reject this job."""
    try:
        trigger_for_job(job, tz)
    except ValueError as e:
        raise ValueError(f'Invalid schedule: {_clean_error(e)}') from e
