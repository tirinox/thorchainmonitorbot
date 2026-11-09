from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dashboard.audit import get_actor
from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services import thresholds

router = APIRouter(prefix='/thresholds', tags=['thresholds'])


class ResetBody(BaseModel):
    direction: Optional[str] = None  # none: all directions


@router.get('')
async def get_thresholds(ctx: DashboardContext = Depends(get_ctx)):
    """Static thresholds of the swap start / finish alerts and the dynamic bar of every direction."""
    return await thresholds.get_thresholds(ctx)


@router.post('/reset')
async def reset_thresholds(body: ResetBody, ctx: DashboardContext = Depends(get_ctx),
                           actor: str = Depends(get_actor)):
    try:
        return await thresholds.reset_thresholds(ctx, body.direction, actor=actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
