"""
Upcoming runs of every scheduled job, for the dashboard calendar: when will which alert go out, and do any of
them land on top of each other.
"""
import math
import time
from datetime import datetime, timezone as dt_timezone
from typing import Optional

from dashboard.channels import channel_to_dict
from dashboard.context import DashboardContext
from dashboard.services.jobs import read_job_stats
from dashboard.services.schedule import get_scheduler_timezone, trigger_for_job, job_schedule_info, _clean_error
from models.sched import SchedJobCfg, SchedVariant, IntervalCfg

DEFAULT_DAYS = 7
MAX_DAYS = 31
# a job firing more often than this is drawn as a band ("every 10 min"), not as hundreds of separate events
FREQUENT_PER_DAY = 24


def interval_seconds(interval: IntervalCfg) -> float:
    return interval.total_seconds


# every window below is half-open, [now, until): an hourly job gives exactly 24 runs a day

def _from_trigger(trigger, now: float, until: float, limit: int) -> list[float]:
    times, previous = [], None
    moment = datetime.fromtimestamp(now, dt_timezone.utc)
    while len(times) <= limit:
        fire = trigger.get_next_fire_time(previous, moment)
        if fire is None or fire.timestamp() >= until or (times and fire.timestamp() <= times[-1]):
            break
        times.append(fire.timestamp())
        previous = moment = fire
    return times


def _from_anchor(anchor: float, period: float, now: float, until: float, limit: int) -> list[float]:
    """An interval job as the bot really runs it: from its known next run, every `period` seconds."""
    if anchor < now:  # stale value: move forward by whole periods
        anchor += math.ceil((now - anchor) / period) * period
    times = []
    t = anchor
    while t < until and len(times) <= limit:
        times.append(t)
        t += period
    return times


def upcoming_fire_times(job: SchedJobCfg, trigger, next_run_ts: Optional[float], applied: bool,
                        now: float, until: float, limit: int,
                        anchor_ts: Optional[float] = None, anchor_period: Optional[float] = None,
                        ) -> tuple[list[float], bool]:
    """
    Returns (unix times in [now, until), approximate). At most limit + 1 times, so the caller can tell
    "exactly limit" from "more than limit".

    Interval jobs count from the anchor the bot saved when it first scheduled them with this period: when it is
    running the job (`applied` and a known next run) we step from that; an unapplied job whose period matches the
    anchor keeps it after Apply too; otherwise we assume an Apply right now (first run one period later) and say it
    is approximate. (APScheduler's own IntervalTrigger would count from the wall clock, not from `now`.)
    """
    if job.variant == SchedVariant.INTERVAL:
        period = interval_seconds(job.interval)
        if applied and next_run_ts:
            return _from_anchor(next_run_ts, period, now, until, limit), False
        if anchor_ts and anchor_period == period:
            return _from_anchor(anchor_ts, period, now, until, limit), False
        return _from_anchor(now + period, period, now, until, limit), True
    return _from_trigger(trigger, now, until, limit), False


async def upcoming_runs(ctx: DashboardContext, days: int = DEFAULT_DAYS, now: Optional[float] = None) -> dict:
    days = max(1, min(int(days), MAX_DAYS))
    now = now or time.time()
    until = now + days * 86400
    limit = FREQUENT_PER_DAY * days

    sched = ctx.scheduler
    jobs: list[SchedJobCfg] = await sched.load_config_from_db(silent=True)
    stats = await read_job_stats(sched, [job.id for job in jobs])
    scheduler_tz = await get_scheduler_timezone(ctx.deps.db)

    items = []
    for job, st in zip(jobs, stats):
        item = {
            'id': job.id,
            'func': job.func,
            'enabled': job.enabled,
            'is_dirty': st.is_dirty,
            'variant': job.variant,
            'schedule': job_schedule_info(job, scheduler_tz)['text'],
            'runs': [],
            'frequent': False,
            'per_day': 0.0,
            'approximate': False,
            'invalid': None,
        }
        try:
            trigger = trigger_for_job(job, scheduler_tz)
        except ValueError as e:
            item['invalid'] = _clean_error(e)
            items.append(item)
            continue

        # the bot only follows the saved config after Apply, and only schedules enabled jobs
        applied = job.enabled and not st.is_dirty
        runs, approximate = upcoming_fire_times(job, trigger, st.next_run_ts, applied, now, until, limit,
                                                st.interval_anchor_ts, st.interval_anchor_period)
        item['approximate'] = approximate
        if len(runs) > limit:
            item['frequent'] = True
            item['per_day'] = FREQUENT_PER_DAY  # "more than", the exact figure is in the schedule text
        else:
            item['runs'] = runs
            item['per_day'] = round(len(runs) / days, 2)
        items.append(item)

    return {
        'now': now,
        'until': until,
        'days': days,
        'scheduler_tz': scheduler_tz,
        'frequent_per_day': FREQUENT_PER_DAY,
        'jobs': items,
        # lets the calendar offer "send to test channel" from an event's preview
        'test_channels': [channel_to_dict(c) for c in getattr(ctx.deps.broadcaster, 'test_channels', [])],
    }
