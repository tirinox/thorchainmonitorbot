import asyncio
import json
import time

from lib.db import DB
from lib.logs import WithLogger
from lib.utils import random_hex
from renderer.const import RESPONSE_STREAM, REQUEST_STREAM


class InfographicRenderer(WithLogger):
    def __init__(self, db: DB, request_stream=REQUEST_STREAM, response_stream=RESPONSE_STREAM,
                 timeout=5.0):
        super().__init__()
        self.db = db
        self._count = 10
        self.timeout = timeout
        self._step_timeout = 1.0
        self.request_stream = request_stream
        self.response_stream = response_stream

    async def render(self, template_name: str, parameters: dict):
        correlation_id = await self._post_message(template_name, parameters or {})
        png_bytes = await self._receive_response(correlation_id, timeout=self.timeout)
        return png_bytes

    async def _post_message(self, name, params):
        correlation_id = str(random_hex())

        message = {
            'template_name': name,
            'parameters': params,
            'correlation_id': correlation_id,
            'reply_to': RESPONSE_STREAM
        }

        # Add message to the request stream
        redis_client = await self.db.get_redis()
        await redis_client.xadd(self.request_stream, {'data': json.dumps(message)})
        return correlation_id

    async def _receive_response(self, correlation_id, timeout=100000.0):
        start_ts = time.monotonic()
        redis_client = await self.db.get_redis()
        while time.monotonic() - start_ts < timeout:
            try:
                messages = await redis_client.xread(
                    streams={RESPONSE_STREAM: '0'},
                    count=self._count,
                    block=int(self._step_timeout * 1000)  # milliseconds
                )

                if messages:
                    for stream, msgs in messages:
                        for msg_id, msg_data in msgs:
                            data = json.loads(msg_data['data'])
                            if data.get('correlation_id') == correlation_id:
                                png_data_hex = data.get('png_data')
                                png_bytes = bytes.fromhex(png_data_hex)
                                self.logger.info(f"Received PNG image: {len(png_bytes)} bytes")
                                return png_bytes

            except Exception as e:
                self.logger.exception(f"Error receiving response: {e!r}. Waiting {self._step_timeout} seconds...")
                await asyncio.sleep(self._step_timeout)

        self.logger.error(f"Timeout receiving response for request: {correlation_id}")
