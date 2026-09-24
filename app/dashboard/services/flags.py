import asyncio

from dashboard.audit import AuditAction, LOCAL_ACTOR
from dashboard.context import DashboardContext
from lib.events import publish_event, EventType
from lib.flagship import Flagship


async def list_flags(ctx: DashboardContext) -> list[dict]:
    flagship: Flagship = ctx.deps.flagship
    keys = await flagship.db.redis.keys(f'{Flagship.DB_KEY_PREFIX}*')
    paths = sorted(key.removeprefix(Flagship.DB_KEY_PREFIX) for key in keys)
    flags, last_changes = await asyncio.gather(
        asyncio.gather(*(flagship.get_flag_object(path) for path in paths)),
        ctx.audit.latest_by_target(AuditAction.FLAG_CHANGES),
    )
    return [
        {
            'path': path,
            'value': flag.value,
            'last_changed_ts': flag.last_changed_ts,
            'last_access_ts': flag.last_access_ts,
            'last_change': last_changes.get(path),  # who changed it from the dashboard, if anyone
        }
        for path, flag in zip(paths, flags)
        if flag is not None
    ]


async def set_flag(ctx: DashboardContext, path: str, value: bool, actor: str = LOCAL_ACTOR):
    flagship: Flagship = ctx.deps.flagship
    old = await flagship.get_flag_object(path)
    await flagship.set_flag(path, value)
    await publish_event(ctx.deps.db, EventType.FLAGS, path=path, value=value)
    if old is None or old.value != value:
        await ctx.audit.record(AuditAction.FLAG_SET, actor, path, old=old.value if old is not None else None, new=value)


async def delete_flag(ctx: DashboardContext, path: str, actor: str = LOCAL_ACTOR):
    flagship: Flagship = ctx.deps.flagship
    old = await flagship.get_flag_object(path)
    await flagship.delete_flag(path)
    await publish_event(ctx.deps.db, EventType.FLAGS, path=path, deleted=True)
    await ctx.audit.record(AuditAction.FLAG_DELETE, actor, path, old=old.value if old is not None else None)
