from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dashboard.audit import get_actor
from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services import achievements

router = APIRouter(prefix='/achievements', tags=['achievements'])


class PreviewBody(BaseModel):
    key: str = Field(min_length=1)
    specialization: str = ''
    # last: the saved record; next: the next milestone; value: as if the metric had `value`
    mode: Literal['last', 'next', 'value'] = 'next'
    value: Optional[int] = Field(None, gt=0)


class StaleBody(BaseModel):
    key: str = Field(min_length=1)
    specialization: str = ''
    stale: bool


@router.get('')
async def list_achievements(ctx: DashboardContext = Depends(get_ctx)):
    """Every achievement: its last milestone, value now, progress to the next milestone and cut-off."""
    return await achievements.list_achievements(ctx)


@router.post('/preview')
async def preview_achievement(body: PreviewBody, ctx: DashboardContext = Depends(get_ctx)):
    """Builds the post (nothing is sent or saved to the records); its images are at /previews/{run_id}/images."""
    try:
        return await achievements.preview_achievement(ctx, body.key, body.specialization, body.mode, body.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@router.post('/stale')
async def set_stale(body: StaleBody, ctx: DashboardContext = Depends(get_ctx), actor: str = Depends(get_actor)):
    """stale=true: the next milestone is saved without a post; stale=false: it is posted."""
    try:
        return await achievements.set_stale(ctx, body.key, body.specialization, body.stale, actor=actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
