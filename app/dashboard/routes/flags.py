from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from dashboard.context import DashboardContext
from dashboard.routes.deps import get_ctx
from dashboard.services import flags

router = APIRouter(prefix='/flags', tags=['flags'])


class FlagBody(BaseModel):
    path: str = Field(min_length=1)
    value: bool


@router.get('')
async def list_flags(ctx: DashboardContext = Depends(get_ctx)):
    return await flags.list_flags(ctx)


@router.put('')
async def set_flag(body: FlagBody, ctx: DashboardContext = Depends(get_ctx)):
    await flags.set_flag(ctx, body.path, body.value)
    return {'ok': True}


@router.delete('')
async def delete_flag(path: str = Query(min_length=1), ctx: DashboardContext = Depends(get_ctx)):
    await flags.delete_flag(ctx, path)
    return {'ok': True}
