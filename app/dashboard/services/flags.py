import asyncio
import logging

from dashboard.audit import AuditAction, LOCAL_ACTOR
from dashboard.context import DashboardContext
from lib.events import publish_event, EventType
from lib.flagship import Flagship, FlagDescriptor


async def _load_flags(flagship: Flagship) -> list[tuple[str, FlagDescriptor]]:
    # one MGET instead of a GET per flag: there are 100+ flags, and firing them all at once exhausts
    # the Redis connection pool (redis-py 8 caps it at 100 by default)
    redis = flagship.db.redis
    keys = sorted(await redis.keys(f'{Flagship.DB_KEY_PREFIX}*'))
    values = await redis.mget(keys) if keys else []
    flags = []
    for key, raw in zip(keys, values):
        if not raw:
            continue
        try:
            flags.append((key.removeprefix(Flagship.DB_KEY_PREFIX), FlagDescriptor.model_validate_json(raw)))
        except ValueError as e:
            logging.warning(f'Skipping unreadable flag {key!r}: {e}')
    return flags


async def list_flags(ctx: DashboardContext) -> list[dict]:
    flags, last_changes = await asyncio.gather(
        _load_flags(ctx.deps.flagship),
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
        for path, flag in flags
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
