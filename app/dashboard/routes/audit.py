from typing import Optional

from fastapi import APIRouter, Depends, Query

from dashboard.audit import MAX_AUDIT_LINES, get_actor
from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx

router = APIRouter(tags=['audit'])


@router.get('/audit')
async def list_audit(actor: Optional[str] = None,
                     action: Optional[str] = None,
                     q: Optional[str] = None,
                     limit: int = Query(200, ge=1, le=MAX_AUDIT_LINES),
                     ctx: DashboardContext = Depends(get_ctx)):
    return await ctx.audit.list(limit=limit, actor=actor, action=action, q=q)


@router.get('/whoami')
async def whoami(actor: str = Depends(get_actor)):
    return {'actor': actor}
