"""
"Is everything OK?" — health checks for the dashboard home page.

Every evaluate_* function is pure (data in, check out) so the thresholds are easy to test and tune.
"""
import asyncio
import logging
import time
from typing import Optional

from dashboard.context import DashboardContext
from dashboard.services.flags import list_flags
from dashboard.services.jobs import list_jobs
from dashboard.services.logs import MAX_LOG_LINES, normalize_level
from dashboard.services.overview import block_scanner_info, fetchers_info
from lib.date_utils import seconds_human


class Status:
    OK = 'ok'
    UNKNOWN = 'unknown'
    WARN = 'warn'
    ERROR = 'error'

    ORDER = [OK, UNKNOWN, WARN, ERROR]  # worst last

    @classmethod
    def worst(cls, statuses) -> str:
        return max(statuses, key=cls.ORDER.index, default=cls.OK)


SCAN_WARN_SEC = 30
SCAN_ERROR_SEC = 5 * 60
LAG_WARN_BLOCKS = 5
LAG_ERROR_BLOCKS = 50

FETCHER_MIN_STALE_SEC = 10 * 60
FETCHER_STALE_PERIODS = 3  # a fetcher is stale after missing this many of its own periods
FETCHER_MIN_SUCCESS_RATE = 90.0

JOB_OVERDUE_GRACE_SEC = 5 * 60
ERROR_WINDOW_SEC = 24 * 60 * 60
MAX_ITEMS = 10


def ago(seconds: float) -> str:
    human = seconds_human(seconds)
    return human if human == 'just now' else f'{human} ago'


def make_check(key: str, title: str, status: str, value: str, detail: str = '',
               link: Optional[dict] = None, items: Optional[list] = None) -> dict:
    return {
        'key': key, 'title': title, 'status': status, 'value': value, 'detail': detail,
        'link': link, 'items': (items or [])[:MAX_ITEMS],
    }


def evaluate_scanner(state: Optional[dict], now: float) -> dict:
    link = {'name': 'overview', 'query': {'tab': 'scanner'}}
    if not state or not state.get('last_scanned_at_ts'):
        return make_check('scanner', 'Block scanner', Status.UNKNOWN, 'no data',
                          'The scanner has not reported its state yet.', link)

    since = now - state['last_scanned_at_ts']
    lag = state.get('lag_behind_thor') or 0
    if since > SCAN_ERROR_SEC or lag > LAG_ERROR_BLOCKS:
        status = Status.ERROR
    elif since > SCAN_WARN_SEC or lag > LAG_WARN_BLOCKS:
        status = Status.WARN
    else:
        status = Status.OK
    detail = f"Block {state.get('last_scanned_block', 0):,} scanned {ago(since)}"
    return make_check('scanner', 'Block scanner', status, f"lag {lag} block{'' if lag == 1 else 's'}", detail, link)


def fetcher_stale_after(sleep_period: float) -> float:
    return max(FETCHER_MIN_STALE_SEC, FETCHER_STALE_PERIODS * (sleep_period or 0))


def evaluate_fetchers(stats: Optional[dict], now: float) -> dict:
    link = {'name': 'overview', 'query': {'tab': 'fetchers'}}
    trackers = (stats or {}).get('trackers') or []
    if not trackers:
        return make_check('fetchers', 'Fetchers', Status.UNKNOWN, 'no data',
                          'No fetcher stats. Is the bot running?', link)

    active = [t for t in trackers if t.get('total_ticks')]  # never-started fetchers are just not used
    stale = [t for t in active if now - t['last_timestamp'] > fetcher_stale_after(t.get('sleep_period'))]
    failing = [t for t in active if t not in stale and t.get('success_rate', 100) < FETCHER_MIN_SUCCESS_RATE]

    items = [{'label': t['name'], 'text': f"no run for {seconds_human(now - t['last_timestamp'])}"} for t in stale]
    items += [{'label': t['name'], 'text': f"success rate {t['success_rate']:.0f}%"} for t in failing]

    if stale:
        status, detail = Status.ERROR, f'{len(stale)} stale'
    elif failing or stats.get('all_paused'):
        status = Status.WARN
        detail = 'all fetchers are paused' if stats.get('all_paused') else f'{len(failing)} with errors'
    else:
        status, detail = Status.OK, 'all running on schedule'
    return make_check('fetchers', 'Fetchers', status, f'{len(active) - len(stale)}/{len(active)} fresh',
                      detail, link, items)


def evaluate_jobs(listing: Optional[dict], now: float) -> dict:
    link = {'name': 'jobs'}
    jobs = (listing or {}).get('jobs') or []
    if not jobs:
        return make_check('jobs', 'Scheduled jobs', Status.WARN, 'none', 'No jobs are configured.', link)

    enabled = [j for j in jobs if j['config']['enabled']]
    failing = [j for j in enabled if j['stats'].get('last_status') == 'error']
    overdue = [j for j in enabled if j not in failing and j['stats'].get('next_run_ts')
               and j['stats']['next_run_ts'] < now - JOB_OVERDUE_GRACE_SEC]

    items = [{'label': j['config']['id'], 'text': j['stats'].get('last_error') or 'last run failed'} for j in failing]
    items += [{'label': j['config']['id'],
               'text': f"expected {ago(now - j['stats']['next_run_ts'])}"} for j in overdue]

    if failing:
        status, detail = Status.ERROR, f'{len(failing)} failing'
    elif overdue:
        status, detail = Status.WARN, f'{len(overdue)} overdue'
    else:
        status, detail = Status.OK, 'last runs succeeded'
    return make_check('jobs', 'Scheduled jobs', status, f'{len(enabled)}/{len(jobs)} enabled', detail, link, items)


def evaluate_config(listing: Optional[dict]) -> dict:
    link = {'name': 'jobs'}
    if listing is None:
        return make_check('config', 'Scheduler config', Status.UNKNOWN, 'no data', '', link)
    if listing.get('is_dirty'):
        return make_check('config', 'Scheduler config', Status.WARN, 'not applied',
                          'Saved changes are waiting for "Apply".', link)
    return make_check('config', 'Scheduler config', Status.OK, 'applied', 'The bot runs the saved config.', link)


def evaluate_flags(flags: Optional[list]) -> dict:
    link = {'name': 'flags', 'query': {'show': 'off'}}
    if flags is None:
        return make_check('flags', 'Feature flags', Status.UNKNOWN, 'no data', '', link)
    off = [f for f in flags if not f['value']]
    items = [{'label': f['path'], 'text': 'disabled'} for f in off]
    if off:
        return make_check('flags', 'Feature flags', Status.WARN, f'{len(off)} off',
                          f'{len(off)} of {len(flags)} flags are disabled', link, items)
    return make_check('flags', 'Feature flags', Status.OK, f'{len(flags)} on', 'Everything is enabled.', link)


def evaluate_errors(raw_logs: Optional[list], now: float) -> dict:
    link = {'name': 'logs', 'query': {'level': 'error'}}
    if raw_logs is None:
        return make_check('errors', 'Scheduler errors', Status.UNKNOWN, 'no data', '', link)
    since = now - ERROR_WINDOW_SEC
    errors = [e for e in raw_logs if normalize_level(e.get('level')) == 'error' and (e.get('_ts') or 0) >= since]
    errors.sort(key=lambda e: -(e.get('_ts') or 0))
    items = [{
        'label': e.get('job_id') or e.get('job') or e.get('action') or '?',
        'text': str(e.get('error') or e.get('reason') or e.get('phase') or 'error'),
        'ts': e.get('_ts'),
    } for e in errors]
    status = Status.WARN if errors else Status.OK
    detail = f'latest {ago(now - errors[0]["_ts"])}' if errors else 'none in the last 24 hours'
    return make_check('errors', 'Scheduler errors', status, f'{len(errors)} in 24h', detail, link, items)


async def _safe(coro, what: str):
    try:
        return await coro
    except Exception as e:
        logging.warning(f'Summary: failed to load {what}: {e!r}')
        return None


async def build_summary(ctx: DashboardContext) -> dict:
    now = time.time()
    scanner, fetchers, listing, flags, logs = await asyncio.gather(
        _safe(block_scanner_info(ctx), 'scanner'),
        _safe(fetchers_info(ctx), 'fetchers'),
        _safe(list_jobs(ctx), 'jobs'),
        _safe(list_flags(ctx), 'flags'),
        _safe(ctx.scheduler.db_log.get_last_logs(MAX_LOG_LINES), 'logs'),
    )
    checks = [
        evaluate_scanner(scanner, now),
        evaluate_fetchers(fetchers, now),
        evaluate_jobs(listing, now),
        evaluate_config(listing),
        evaluate_errors(logs, now),
        evaluate_flags(flags),
    ]
    return {
        'now': now,
        'status': Status.worst(c['status'] for c in checks),
        'checks': checks,
    }
