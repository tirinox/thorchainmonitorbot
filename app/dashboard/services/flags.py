import asyncio

from dashboard.context import DashboardContext
from lib.flagship import Flagship


async def list_flags(ctx: DashboardContext) -> list[dict]:
    flagship: Flagship = ctx.deps.flagship
    keys = await flagship.db.redis.keys(f'{Flagship.DB_KEY_PREFIX}*')
    paths = sorted(key.removeprefix(Flagship.DB_KEY_PREFIX) for key in keys)
    flags = await asyncio.gather(*(flagship.get_flag_object(path) for path in paths))
    return [
        {
            'path': path,
            'value': flag.value,
            'last_changed_ts': flag.last_changed_ts,
            'last_access_ts': flag.last_access_ts,
        }
        for path, flag in zip(paths, flags)
        if flag is not None
    ]


async def set_flag(ctx: DashboardContext, path: str, value: bool):
    await ctx.deps.flagship.set_flag(path, value)


async def delete_flag(ctx: DashboardContext, path: str):
    await ctx.deps.flagship.delete_flag(path)
