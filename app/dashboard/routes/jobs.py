import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError

from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services import jobs
from dashboard.services.jobs import JobPayload, JobNotFound

router = APIRouter(tags=['scheduler'])


class ToggleBody(BaseModel):
    enabled: bool


class RunJobBody(BaseModel):
    timeout: float = Field(30.0, ge=5, le=3600)


class RunFunctionBody(RunJobBody):
    func: str
    args: dict[str, Any] = Field(default_factory=dict)


async def _handle(coro):
    """Maps service/RPC exceptions to HTTP errors."""
    try:
        return await coro
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


@router.get('/jobs')
async def list_jobs(ctx: DashboardContext = Depends(get_ctx)):
    return await jobs.list_jobs(ctx)


@router.post('/jobs')
async def create_job(payload: JobPayload, ctx: DashboardContext = Depends(get_ctx)):
    job = await _handle(jobs.save_job(ctx, payload))
    return job.model_dump(mode='json')


@router.put('/jobs/{job_id}')
async def update_job(job_id: str, payload: JobPayload, ctx: DashboardContext = Depends(get_ctx)):
    job = await _handle(jobs.save_job(ctx, payload, job_id=job_id))
    return job.model_dump(mode='json')


@router.delete('/jobs/{job_id}')
async def delete_job(job_id: str, ctx: DashboardContext = Depends(get_ctx)):
    await _handle(jobs.delete_job(ctx, job_id))
    return {'ok': True}


@router.post('/jobs/{job_id}/enabled')
async def set_enabled(job_id: str, body: ToggleBody, ctx: DashboardContext = Depends(get_ctx)):
    await _handle(jobs.set_job_enabled(ctx, job_id, body.enabled))
    return {'ok': True}


@router.post('/jobs/{job_id}/run')
async def run_job(job_id: str, body: RunJobBody, ctx: DashboardContext = Depends(get_ctx)):
    return await _handle(jobs.run_job_now(ctx, job_id, body.timeout))


@router.post('/run-now')
async def run_function(body: RunFunctionBody, ctx: DashboardContext = Depends(get_ctx)):
    return await _handle(jobs.run_function_now(ctx, body.func, body.args, body.timeout))


@router.post('/scheduler/reload')
async def reload_scheduler(ctx: DashboardContext = Depends(get_ctx)):
    return await _handle(jobs.reload_scheduler(ctx))
