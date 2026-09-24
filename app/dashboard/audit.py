from typing import Any, Optional

from fastapi import Request

from lib.db import DB
from lib.log_db import CircularLog

AUDIT_LOG_PREFIX = 'DashboardAudit'
MAX_AUDIT_LINES = 5000
LOCAL_ACTOR = 'local'


class AuditAction:
    JOB_CREATE = 'job.create'
    JOB_UPDATE = 'job.update'
    JOB_DELETE = 'job.delete'
    JOB_RESTORE = 'job.restore'
    JOB_ENABLE = 'job.enable'
    JOB_DISABLE = 'job.disable'
    JOB_RUN = 'job.run'
    FUNCTION_RUN = 'function.run'
    SCHEDULER_APPLY = 'scheduler.apply'
    FLAG_SET = 'flag.set'
    FLAG_DELETE = 'flag.delete'

    DESTRUCTIVE = {JOB_DELETE, FLAG_DELETE}


def get_actor(request: Request) -> str:
    """
    Who is acting. nginx puts the basic-auth user into X-Remote-User and always overwrites that header,
    and the dashboard port is only reachable through nginx, so a browser cannot fake it.
    """
    return (request.headers.get('x-remote-user') or '').strip() or LOCAL_ACTOR


def _flatten(d: Any, prefix='') -> dict[str, Any]:
    if not isinstance(d, dict):
        return {prefix: d}
    flat = {}
    for key, value in d.items():
        path = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(value, dict) and value:
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def diff_dicts(old: Optional[dict], new: Optional[dict]) -> dict[str, list]:
    """{"a.b": [old, new]} for every leaf that differs; nested dicts become dotted paths, lists compare whole."""
    old_flat, new_flat = _flatten(old or {}), _flatten(new or {})
    changes = {}
    for key in sorted(set(old_flat) | set(new_flat)):
        before, after = old_flat.get(key), new_flat.get(key)
        if before != after:
            changes[key] = [before, after]
    return changes


class AuditLog:
    """Who changed what in the dashboard. Entries also go out as live `log` events (source=DashboardAudit)."""

    def __init__(self, db: DB):
        self._log = CircularLog(AUDIT_LOG_PREFIX, db, max_lines=MAX_AUDIT_LINES)

    async def record(self, action: str, actor: str, target: Optional[str] = None, **details):
        level = 'warning' if action in AuditAction.DESTRUCTIVE else 'info'
        await self._log.add_log_safe(action, level, actor=actor, target=target, **details)

    async def list(self, limit: int = 200, actor: Optional[str] = None, action: Optional[str] = None,
                   q: Optional[str] = None) -> dict:
        entries = [normalize_audit_entry(e) for e in await self._log.get_last_logs(MAX_AUDIT_LINES)]
        return filter_audit(entries, limit=limit, actor=actor, action=action, q=q)


def normalize_audit_entry(raw: dict) -> dict:
    known = ('_ts', 'level', 'action', 'actor', 'target')
    return {
        'ts': raw.get('_ts'),
        'level': raw.get('level') or 'info',
        'action': raw.get('action') or '?',
        'actor': raw.get('actor') or '?',
        'target': raw.get('target'),
        'details': {k: v for k, v in raw.items() if k not in known},
    }


def filter_audit(entries: list[dict], limit=200, actor=None, action=None, q=None) -> dict:
    text = (q or '').strip().lower()

    def matches(e):
        if actor and e['actor'] != actor:
            return False
        if action and e['action'] != action:
            return False
        if text and text not in f"{e['action']} {e['actor']} {e['target']} {e['details']}".lower():
            return False
        return True

    filtered = [e for e in entries if matches(e)]
    return {
        'total': len(entries),
        'matched': len(filtered),
        'items': filtered[:max(1, limit)],
        'facets': {
            'actors': sorted({e['actor'] for e in entries}),
            'actions': sorted({e['action'] for e in entries}),
        },
    }
