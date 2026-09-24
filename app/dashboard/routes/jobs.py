import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError

from dashboard.audit import get_actor
from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services import jobs
from dashboard.services.schedule import get_scheduler_timezone, preview_schedule
from dashboard.runs import RunConflict
from dashboard.services.jobs import JobPayload, JobNotFound, JobConflict

router = APIRouter(tags=['scheduler'])


class ToggleBody(BaseModel):
    enabled: bool


class RestoreBody(BaseModel):
    config: dict[str, Any]  # as saved in the job.delete audit entry


class RunJobBody(BaseModel):
    # how long the dashboard waits for the bot's answer; the HTTP request itself returns at once
    timeout: float = Field(3600.0, ge=5, le=6 * 3600)


class RunFunctionBody(RunJobBody):
    func: str
    args: dict[str, Any] = Field(default_factory=dict)


async def _handle(coro):
    """Maps service/RPC exceptions to HTTP errors."""
    try:
        return await coro
    except RunConflict as e:
        raise HTTPException(409, str(e))
    except JobConflict as e:
        raise HTTPException(409, f'A job with id {e.args[0]!r} already exists')
    except JobNotFound as e:
        raise HTTPException(404, f'Job {e.args[0]!r} not found')
    except ValidationError as e:
        raise HTTPException(422, jsonable_encoder(e.errors(include_url=False, include_context=False)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, 'No response from the bot in time; the job may still be running. Check the logs.')
    except RuntimeError as e:
        raise HTTPException(502, str(e))


class SchedulePreviewBody(BaseModel):
    variant: str
    interval: Optional[dict[str, Any]] = None
    cron: Optional[dict[str, Any]] = None
    date: Optional[dict[str, Any]] = None
    tz: Optional[str] = None  # the viewer's timezone, for local equivalents of fixed times
    count: int = Field(5, ge=1, le=20)


@router.get('/jobs')
async def list_jobs(tz: Optional[str] = None, ctx: DashboardContext = Depends(get_ctx)):
    return await jobs.list_jobs(ctx, viewer_tz=tz)


@router.post('/schedule/preview')
async def schedule_preview(body: SchedulePreviewBody, ctx: DashboardContext = Depends(get_ctx)):
    """Describes a schedule and lists its next runs, exactly as the bot's APScheduler would compute them."""
    scheduler_tz = await get_scheduler_timezone(ctx.deps.db)
    return preview_schedule(body.variant, body.interval, body.cron, body.date, scheduler_tz, body.tz, body.count)


@router.post('/jobs')
async def create_job(payload: JobPayload, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    job = await _handle(jobs.save_job(ctx, payload, actor=actor))
    return job.model_dump(mode='json')


@router.post('/jobs/restore')
async def restore_job(body: RestoreBody, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    job = await _handle(jobs.restore_job(ctx, body.config, actor=actor))
    return job.model_dump(mode='json')


@router.put('/jobs/{job_id}')
async def update_job(job_id: str, payload: JobPayload, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    job = await _handle(jobs.save_job(ctx, payload, job_id=job_id, actor=actor))
    return job.model_dump(mode='json')


@router.delete('/jobs/{job_id}')
async def delete_job(job_id: str, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    await _handle(jobs.delete_job(ctx, job_id, actor=actor))
    return {'ok': True}


@router.post('/jobs/{job_id}/enabled')
async def set_enabled(job_id: str, body: ToggleBody, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    await _handle(jobs.set_job_enabled(ctx, job_id, body.enabled, actor=actor))
    return {'ok': True}


@router.post('/jobs/{job_id}/run', status_code=202)
async def run_job(job_id: str, body: RunJobBody, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    """Starts the job in the bot and returns immediately; progress comes as `run` events."""
    return await _handle(jobs.start_job_run(ctx, job_id, body.timeout, actor=actor))


@router.post('/run-now', status_code=202)
async def run_function(body: RunFunctionBody, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    return await _handle(jobs.start_function_run(ctx, body.func, body.args, body.timeout, actor=actor))


@router.get('/runs')
async def list_runs(ctx: DashboardContext = Depends(get_ctx)):
    """Manual runs started from this dashboard process (active and recently finished)."""
    return ctx.runs.list()


@router.post('/scheduler/reload')
async def reload_scheduler(ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    return await _handle(jobs.reload_scheduler(ctx, actor=actor))
