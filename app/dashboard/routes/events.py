import asyncio
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from dashboard.context import DashboardContext
from dashboard.events import format_sse
from dashboard.routes.deps import get_ctx

router = APIRouter(tags=['events'])

HEARTBEAT_SEC = 15  # well below nginx's default 60 s proxy_read_timeout
RECONNECT_MS = 3000


@router.get('/events')
async def events(request: Request, ctx: DashboardContext = Depends(get_ctx)):
    """Server-Sent Events: one JSON object per message, with a `type` field (see lib.events.EventType)."""
    sub = ctx.events.subscribe()

    async def stream():
        try:
            yield f'retry: {RECONNECT_MS}\n\n'
            yield format_sse({'type': 'hello', 'ts': time.time()})
            while not sub.overflowed and not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(sub.queue.get(), HEARTBEAT_SEC)
                except asyncio.TimeoutError:
                    yield ': ping\n\n'
                    continue
                yield format_sse(event)
        finally:
            ctx.events.unsubscribe(sub)

    return StreamingResponse(stream(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',  # tells nginx not to buffer the stream
    })
