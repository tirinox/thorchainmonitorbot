from fastapi import APIRouter, Depends

from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services.summary import build_summary

router = APIRouter(tags=['summary'])


@router.get('/summary')
async def summary(ctx: DashboardContext = Depends(get_ctx)):
    """Health checks for the home page: overall status plus one entry per check."""
    return await build_summary(ctx)
