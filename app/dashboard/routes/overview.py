from fastapi import APIRouter, Depends

from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services import overview

router = APIRouter(prefix='/overview', tags=['overview'])


@router.get('/dedup')
async def dedup(ctx: DashboardContext = Depends(get_ctx)):
    return await overview.dedup_info(ctx)


@router.get('/fetchers')
async def fetchers(ctx: DashboardContext = Depends(get_ctx)):
    return await overview.fetchers_info(ctx)


@router.get('/curve')
async def curve(ctx: DashboardContext = Depends(get_ctx)):
    return await overview.curve_info(ctx)


@router.get('/stats')
async def stats(ctx: DashboardContext = Depends(get_ctx)):
    return await overview.user_stats(ctx)


@router.get('/transfers')
async def transfers(ctx: DashboardContext = Depends(get_ctx)):
    return await overview.rune_transfer_stats(ctx)


@router.get('/scanner')
async def scanner(ctx: DashboardContext = Depends(get_ctx)):
    return await overview.block_scanner_info(ctx)
