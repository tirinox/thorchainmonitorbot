"""
Lightweight live events for the admin dashboard.

The bot publishes small JSON messages to one Redis pub/sub channel whenever something the dashboard
shows changes (a scheduler log line, scanner state, fetcher stats...). The dashboard fans them out to
browsers over SSE. Events are best-effort notifications: publishing never raises, and nothing is stored.
"""
import json
import logging
import time

from lib.db import DB

DASHBOARD_EVENTS_CHANNEL = 'Dashboard:Events'


class EventType:
    LOG = 'log'  # a CircularLog entry was added (scheduler actions and job runs)
    SCANNER = 'scanner'  # block scanner state saved
    FETCHERS = 'fetchers'  # fetcher stats saved
    FLAGS = 'flags'  # a feature flag was changed or deleted
    RUN = 'run'  # a manual "run now" started / finished (published by the dashboard)


async def publish_event(db: DB, event_type: str, **payload):
    redis = db.redis if db else None
    if redis is None:
        return
    try:
        message = json.dumps({'type': event_type, 'ts': time.time(), **payload}, default=str)
        await redis.publish(DASHBOARD_EVENTS_CHANNEL, message)
    except Exception as e:
        logging.warning(f'Failed to publish dashboard event {event_type!r}: {e!r}')


class EventThrottle:
    """Lets an event through at most once per `min_interval` seconds (per key)."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = {}

    def allow(self, key='') -> bool:
        now = time.monotonic()
        if now - self._last.get(key, 0.0) < self.min_interval:
            return False
        self._last[key] = now
        return True
