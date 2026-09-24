from typing import Optional

from fastapi import APIRouter, Depends, Query

from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services import logs

router = APIRouter(tags=['logs'])


@router.get('/logs')
async def get_logs(action: Optional[str] = None,
                   phase: Optional[str] = None,
                   job: Optional[str] = None,
                   level: Optional[str] = None,
                   q: Optional[str] = None,
                   limit: int = Query(500, ge=1, le=logs.MAX_LOG_LINES),
                   ctx: DashboardContext = Depends(get_ctx)):
    return await logs.get_logs(ctx, action=action, phase=phase, job=job, level=level, q=q, limit=limit)
