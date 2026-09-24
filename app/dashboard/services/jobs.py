import asyncio
import time
from typing import Any, Optional, Literal

from pydantic import BaseModel, Field

from dashboard.channels import channel_to_dict, resolve_job_channels, format_unknown_channel
from dashboard.context import DashboardContext
from models.sched import SchedJobCfg, IntervalCfg, CronCfg, DateCfg, SchedVariant
from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler, JobStatsModel


class JobNotFound(LookupError):
    pass


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


def schedule_human_readable(job: SchedJobCfg) -> str:
    if job.variant == SchedVariant.INTERVAL and job.interval:
        return job.interval.human_readable
    if job.variant == SchedVariant.CRON and job.cron:
        return job.cron.human_readable
    if job.variant == SchedVariant.DATE and job.date:
        return job.date.human_readable
    return ''


def _stats_to_dict(stats: JobStatsModel) -> dict:
    return {**stats.model_dump(), 'avg_elapsed': stats.avg_elapsed}


async def list_jobs(ctx: DashboardContext) -> dict:
    sched = ctx.scheduler
    jobs: list[SchedJobCfg] = await sched.load_config_from_db(silent=True)
    configured_channels = list(ctx.deps.broadcaster.channels)

    all_stats = await asyncio.gather(
        sched.get_job_stats(PublicScheduler.ANY_JOB_SPECIAL_ID),
        *(sched.get_job_stats(job.id) for job in jobs),
    )
    any_job_stats, job_stats = all_stats[0], all_stats[1:]

    items = []
    for job, stats in zip(jobs, job_stats):
        resolved, unknown = resolve_job_channels(job.args.get('channels'), configured_channels)
        items.append({
            'config': job.model_dump(mode='json'),
            'stats': _stats_to_dict(stats),
            'schedule': schedule_human_readable(job),
            'channels': {
                'resolved': [channel_to_dict(c) for c in resolved],
                'unknown': [format_unknown_channel(c) for c in unknown],
            },
        })

    distribution = dict(sched.job_distribution(jobs))
    return {
        'now': time.time(),
        'jobs': items,
        'is_dirty': any_job_stats.is_dirty or any(s.is_dirty for s in job_stats),
        'distribution': distribution,
        'available_types': list(PublicAlertJobExecutor.AVAILABLE_TYPES.keys()),
        'absent_types': PublicAlertJobExecutor.get_function_that_are_absent(list(distribution.keys())),
        'channels': [channel_to_dict(c) for c in configured_channels],
    }


async def save_job(ctx: DashboardContext, payload: JobPayload, job_id: Optional[str] = None) -> SchedJobCfg:
    """
    Creates a new job (job_id is None) or replaces an existing one.
    Raises pydantic.ValidationError if the resulting config is invalid.
    """
    async with ctx.sched_lock:
        sched = ctx.scheduler
        await sched.load_config_from_db(silent=True)

        is_edit = job_id is not None
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
        await sched.add_new_job(job_cfg, allow_replace=is_edit)
        return job_cfg


async def delete_job(ctx: DashboardContext, job_id: str):
    async with ctx.sched_lock:
        sched = ctx.scheduler
        await sched.load_config_from_db(silent=True)
        if not sched.find_job_by_id(job_id):
            raise JobNotFound(job_id)
        await sched.delete_job(job_id)


async def set_job_enabled(ctx: DashboardContext, job_id: str, enabled: bool):
    async with ctx.sched_lock:
        sched = ctx.scheduler
        await sched.load_config_from_db(silent=True)
        if not sched.find_job_by_id(job_id):
            raise JobNotFound(job_id)
        await sched.toggle_job_enabled(job_id, enabled)


def ensure_known_function(func: str):
    if func not in PublicAlertJobExecutor.AVAILABLE_TYPES:
        raise ValueError(f'Unknown job function: {func!r}')


async def start_job_run(ctx: DashboardContext, job_id: str, timeout: float) -> dict:
    await ctx.scheduler.load_config_from_db(silent=True)
    if not ctx.scheduler.find_job_by_id(job_id):
        raise JobNotFound(job_id)
    return ctx.runs.start(job_id=job_id, timeout=timeout).to_dict()


async def start_function_run(ctx: DashboardContext, func: str, args: dict, timeout: float) -> dict:
    ensure_known_function(func)
    return ctx.runs.start(func=func, args=args, timeout=timeout).to_dict()


async def reload_scheduler(ctx: DashboardContext) -> dict:
    sched = ctx.scheduler
    result = await sched.post_command(sched.COMMAND_RELOAD)
    return {'ok': result == 'reloaded', 'result': result}
