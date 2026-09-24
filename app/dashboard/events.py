import asyncio
import json
import logging
from typing import Optional

from lib.db import DB
from lib.events import DASHBOARD_EVENTS_CHANNEL
from lib.interchan import PubSubChannel


class EventSubscriber:
    """One connected browser. If it cannot keep up, it is closed and the browser reconnects and resyncs."""

    def __init__(self, max_queue: int):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
        self.overflowed = False

    def push(self, event: dict) -> bool:
        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self.overflowed = True
            return False


class EventHub:
    """Single Redis pub/sub subscription fanned out to any number of SSE clients."""

    MAX_QUEUE = 500

    def __init__(self, db: Optional[DB]):
        self._subscribers: set[EventSubscriber] = set()
        self._channel = PubSubChannel(db, DASHBOARD_EVENTS_CHANNEL, self._on_message) if db else None

    def start(self):
        if self._channel:
            self._channel.start()

    async def stop(self):
        if self._channel:
            await self._channel.stop()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> EventSubscriber:
        sub = EventSubscriber(self.MAX_QUEUE)
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: EventSubscriber):
        self._subscribers.discard(sub)

    def dispatch(self, event: dict):
        for sub in list(self._subscribers):
            if not sub.push(event):
                logging.warning('Dashboard SSE client is too slow; dropping it')
                self.unsubscribe(sub)

    async def _on_message(self, _channel, data):
        if isinstance(data, dict) and data.get('type'):
            self.dispatch(data)


def format_sse(event: dict) -> str:
    # every event goes as the default "message" type; the JSON carries its own "type"
    return f"data: {json.dumps(event, default=str)}\n\n"
