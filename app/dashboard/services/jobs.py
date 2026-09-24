import asyncio
import time
from typing import Any, Optional, Literal

from pydantic import BaseModel, Field

from dashboard.audit import AuditAction, LOCAL_ACTOR, diff_dicts
from dashboard.channels import channel_to_dict, resolve_job_channels, format_unknown_channel
from dashboard.context import DashboardContext
from dashboard.services.logs import MAX_LOG_LINES
from dashboard.services.schedule import get_scheduler_timezone, job_schedule_info, validate_job_schedule
from models.sched import SchedJobCfg, IntervalCfg, CronCfg, DateCfg, SchedVariant
from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler, JobStatsModel


class JobNotFound(LookupError):
    pass


class JobConflict(Exception):
    """A job with this id already exists."""


class JobPayload(BaseModel):
    """Job form as sent by the frontend. `channels` is stored into `args.channels`."""
    func: Optional[str] = None  # ignored on edit: the function of an existing job cannot change
    enabled: bool = False
    variant: Literal['interval', 'cron', 'date']
    args: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list)

    interval: Optional[IntervalCfg] = None
    cron: Optional[CronCfg] = None
    date: Optional[DateCfg] = None

    max_instances: int = Field(1, ge=1, le=100)
    coalesce: bool = True
    misfire_grace_time: Optional[int] = Field(None, ge=0, le=3600)


def _stats_to_dict(stats: JobStatsModel) -> dict:
    return {**stats.model_dump(), 'avg_elapsed': stats.avg_elapsed}


RUN_HISTORY_LEN = 10
_RUN_OUTCOMES = {'complete': 'ok', 'failed': 'error', 'skipped': 'skipped'}


def run_history(raw_logs: list[dict], job_ids, limit: int = RUN_HISTORY_LEN) -> dict[str, list[dict]]:
    """Newest-first scheduler log -> {job_id: last `limit` finished runs, oldest first}."""
    history = {job_id: [] for job_id in job_ids}
    for entry in raw_logs:
        if entry.get('action') != 'run':
            continue
        outcome = _RUN_OUTCOMES.get(entry.get('phase'))
        runs = history.get(entry.get('job_id'))
        if outcome is None or runs is None or len(runs) >= limit:
            continue
        runs.append({
            'ts': entry.get('_ts'),
            'status': outcome,
            'elapsed': entry.get('elapsed'),
            'error': entry.get('error'),
            'manual': bool(entry.get('run_id')),  # started from the dashboard
        })
    return {job_id: runs[::-1] for job_id, runs in history.items()}


async def list_jobs(ctx: DashboardContext, viewer_tz: Optional[str] = None) -> dict:
    """`viewer_tz` (IANA name) adds the viewer's local equivalents of fixed cron times."""
    sched = ctx.scheduler
    jobs: list[SchedJobCfg] = await sched.load_config_from_db(silent=True)
    scheduler_tz = await get_scheduler_timezone(ctx.deps.db)
    configured_channels = list(ctx.deps.broadcaster.channels)

    raw_logs, *all_stats = await asyncio.gather(
        sched.db_log.get_last_logs(MAX_LOG_LINES),
        sched.get_job_stats(PublicScheduler.ANY_JOB_SPECIAL_ID),
        *(sched.get_job_stats(job.id) for job in jobs),
    )
    any_job_stats, job_stats = all_stats[0], all_stats[1:]
    history = run_history(raw_logs, [job.id for job in jobs])

    items = []
    for job, stats in zip(jobs, job_stats):
        resolved, unknown = resolve_job_channels(job.args.get('channels'), configured_channels)
        items.append({
            'config': job.model_dump(mode='json'),
            'stats': _stats_to_dict(stats),
            'schedule': job_schedule_info(job, scheduler_tz, viewer_tz),
            'history': history[job.id],
            'channels': {
                'resolved': [channel_to_dict(c) for c in resolved],
                'unknown': [format_unknown_channel(c) for c in unknown],
            },
        })

    distribution = dict(sched.job_distribution(jobs))
    return {
        'now': time.time(),
        'scheduler_tz': scheduler_tz,
        'jobs': items,
        'is_dirty': any_job_stats.is_dirty or any(s.is_dirty for s in job_stats),
        'distribution': distribution,
        'available_types': list(PublicAlertJobExecutor.AVAILABLE_TYPES.keys()),
        'absent_types': PublicAlertJobExecutor.get_function_that_are_absent(list(distribution.keys())),
        'channels': [channel_to_dict(c) for c in configured_channels],
    }


async def save_job(ctx: DashboardContext, payload: JobPayload, job_id: Optional[str] = None,
                   actor: str = LOCAL_ACTOR) -> SchedJobCfg:
    """
    Creates a new job (job_id is None) or replaces an existing one.
    Raises pydantic.ValidationError if the resulting config is invalid, ValueError if APScheduler would reject it.
    """
    scheduler_tz = await get_scheduler_timezone(ctx.deps.db)
    async with ctx.sched_lock:
        sched = ctx.scheduler
        await sched.load_config_from_db(silent=True)

        is_edit = job_id is not None
        existing = None
        if is_edit:
            existing = sched.find_job_by_id(job_id)
            if not existing:
                raise JobNotFound(job_id)
            func = existing.func
        else:
            func = payload.func
            ensure_known_function(func)
            job_id = f"{func}_job_{int(time.time())}"

        args = dict(payload.args)
        if payload.channels:
            args['channels'] = list(payload.channels)
        else:
            args.pop('channels', None)

        job_cfg = SchedJobCfg(
            id=job_id,
            func=func,
            enabled=payload.enabled,
            variant=payload.variant,
            args=args,
            interval=payload.interval if payload.variant == SchedVariant.INTERVAL else None,
            cron=payload.cron if payload.variant == SchedVariant.CRON else None,
            date=payload.date if payload.variant == SchedVariant.DATE else None,
            max_instances=payload.max_instances,
            coalesce=payload.coalesce,
            misfire_grace_time=payload.misfire_grace_time,
        )
        # an invalid trigger would make the bot's "Apply" fail on this job and skip the rest
        validate_job_schedule(job_cfg, scheduler_tz)
        await sched.add_new_job(job_cfg, allow_replace=is_edit)

    if existing:
        changes = diff_dicts(existing.model_dump(mode='json'), job_cfg.model_dump(mode='json'))
        await ctx.audit.record(AuditAction.JOB_UPDATE, actor, job_id, func=func, changes=changes)
    else:
        await ctx.audit.record(AuditAction.JOB_CREATE, actor, job_id, func=func, variant=job_cfg.variant,
                               schedule=job_schedule_info(job_cfg, scheduler_tz)['text'], enabled=job_cfg.enabled)
    return job_cfg


async def restore_job(ctx: DashboardContext, config: dict, actor: str = LOCAL_ACTOR) -> SchedJobCfg:
    """Re-creates a deleted job from the config saved in its `job.delete` audit entry."""
    job_cfg = SchedJobCfg(**config)  # pydantic.ValidationError if the saved config no longer fits the model
    ensure_known_function(job_cfg.func)
    validate_job_schedule(job_cfg, await get_scheduler_timezone(ctx.deps.db))
    async with ctx.sched_lock:
        sched = ctx.scheduler
        await sched.load_config_from_db(silent=True)
        if sched.find_job_by_id(job_cfg.id):
            raise JobConflict(job_cfg.id)
        await sched.add_new_job(job_cfg)
    await ctx.audit.record(AuditAction.JOB_RESTORE, actor, job_cfg.id, func=job_cfg.func, enabled=job_cfg.enabled)
    return job_cfg


async def delete_job(ctx: DashboardContext, job_id: str, actor: str = LOCAL_ACTOR):
    async with ctx.sched_lock:
        sched = ctx.scheduler
        await sched.load_config_from_db(silent=True)
        job = sched.find_job_by_id(job_id)
        if not job:
            raise JobNotFound(job_id)
        await sched.delete_job(job_id)
    await ctx.audit.record(AuditAction.JOB_DELETE, actor, job_id, func=job.func, config=job.model_dump(mode='json'))


async def set_job_enabled(ctx: DashboardContext, job_id: str, enabled: bool, actor: str = LOCAL_ACTOR):
    async with ctx.sched_lock:
        sched = ctx.scheduler
        await sched.load_config_from_db(silent=True)
        job = sched.find_job_by_id(job_id)
        if not job:
            raise JobNotFound(job_id)
        was_enabled = job.enabled
        await sched.toggle_job_enabled(job_id, enabled)
    if was_enabled != enabled:
        action = AuditAction.JOB_ENABLE if enabled else AuditAction.JOB_DISABLE
        await ctx.audit.record(action, actor, job_id, func=job.func)


def ensure_known_function(func: str):
    if func not in PublicAlertJobExecutor.AVAILABLE_TYPES:
        raise ValueError(f'Unknown job function: {func!r}')


async def start_job_run(ctx: DashboardContext, job_id: str, timeout: float, actor: str = LOCAL_ACTOR) -> dict:
    await ctx.scheduler.load_config_from_db(silent=True)
    job = ctx.scheduler.find_job_by_id(job_id)
    if not job:
        raise JobNotFound(job_id)
    run = ctx.runs.start(job_id=job_id, timeout=timeout, actor=actor)
    await ctx.audit.record(AuditAction.JOB_RUN, actor, job_id, func=job.func, run_id=run.run_id)
    return run.to_dict()


async def start_function_run(ctx: DashboardContext, func: str, args: dict, timeout: float,
                             actor: str = LOCAL_ACTOR) -> dict:
    ensure_known_function(func)
    run = ctx.runs.start(func=func, args=args, timeout=timeout, actor=actor)
    await ctx.audit.record(AuditAction.FUNCTION_RUN, actor, func, args=args, run_id=run.run_id)
    return run.to_dict()


async def reload_scheduler(ctx: DashboardContext, actor: str = LOCAL_ACTOR) -> dict:
    sched = ctx.scheduler
    result = await sched.post_command(sched.COMMAND_RELOAD)
    ok = result == 'reloaded'
    await ctx.audit.record(AuditAction.SCHEDULER_APPLY, actor, ok=ok, result=result)
    return {'ok': ok, 'result': result}
