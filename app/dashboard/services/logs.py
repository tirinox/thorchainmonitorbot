import json
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from dashboard.context import DashboardContext

MAX_LOG_LINES = 10_000
KNOWN_COLUMNS = ('_ts', 'level', 'action', 'job', 'phase')


def normalize_level(level) -> str:
    s = str(level or 'info').lower()
    if 'error' in s or 'exception' in s:
        return 'error'
    if 'warn' in s:
        return 'warning'
    return 'info'


def normalize_entry(raw: dict) -> dict:
    return {
        'ts': raw.get('_ts'),
        'level': normalize_level(raw.get('level')),
        'action': raw.get('action') or '-',
        'job': raw.get('job') or '-',
        'phase': raw.get('phase') or '-',
        'details': {k: v for k, v in raw.items() if k not in KNOWN_COLUMNS and v not in (None, '')},
    }


def _matches_text(raw: dict, text: str) -> bool:
    return text in json.dumps(raw, ensure_ascii=False, default=str).lower()


def _day(ts) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).date().isoformat()


def filter_logs(raw_logs: list[dict],
                action: Optional[str] = None,
                phase: Optional[str] = None,
                job: Optional[str] = None,
                level: Optional[str] = None,
                q: Optional[str] = None,
                limit: int = 500) -> dict:
    entries = [(raw, normalize_entry(raw)) for raw in raw_logs]

    facets = {
        'actions': sorted({e['action'] for _, e in entries}),
        'phases': sorted({e['phase'] for _, e in entries}),
        'jobs': sorted({e['job'] for _, e in entries}),
    }

    text = (q or '').strip().lower()
    filtered = [
        e for raw, e in entries
        if (not action or e['action'] == action)
           and (not phase or e['phase'] == phase)
           and (not job or e['job'] == job)
           and (not level or e['level'] == level)
           and (not text or _matches_text(raw, text))
    ]

    histogram = Counter((_day(e['ts']), e['level']) for e in filtered if e['ts'])
    return {
        'total': len(raw_logs),
        'matched': len(filtered),
        'items': filtered[:max(1, limit)],
        'facets': facets,
        'histogram': [
            {'date': date, 'level': lvl, 'count': count}
            for (date, lvl), count in sorted(histogram.items())
        ],
    }


async def get_logs(ctx: DashboardContext, **filters) -> dict:
    # newest first
    raw_logs = await ctx.scheduler.db_log.get_last_logs(MAX_LOG_LINES)
    return filter_logs(raw_logs, **filters)
