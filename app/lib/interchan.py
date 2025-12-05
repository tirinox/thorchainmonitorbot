import asyncio
import json
import logging
import uuid

from lib.db import DB
from lib.logs import WithLogger


class PubSubChannel:
    def __init__(self, db: DB, channel: str, callback):
        self.db = db
        self.channel = channel
        self.callback = callback

        self._task = None
        self._running = False

    async def post_message(self, message: dict):
        await self.db.redis.publish(self.channel, json.dumps(message))

    def start(self):
        if self._running:
            raise Exception("Already running")
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _listen_loop(self):
        pubsub = self.db.redis.pubsub()
        await pubsub.subscribe(self.channel)

        try:
            async for msg in pubsub.listen():
                if not self._running:
                    break

                try:
                    if msg["type"] == "message":
                        data = msg["data"]
                        if data and self.callback:
                            data = json.loads(data)
                            await self.callback(self.channel, data)
                except Exception as e:
                    logging.exception(f'Error processing message: {e}')

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.exception(f'Error in subscriber listen loop: {e}')
        finally:
            await pubsub.close()


class SimpleRPC(WithLogger):
    def __init__(self, db: DB, channel_prefix: str):
        super().__init__()
        self.db = db
        self._call_listener = PubSubChannel(db, f'{channel_prefix}:Call', self._call_callback)
        self._response_listener = PubSubChannel(db, f'{channel_prefix}:Response', self._response_callback)
        self._receiver_callback = None
        self._mode = ''
        self._response_collection = {}

    async def _call_callback(self, _, data):
        call_id = data.get('__call_id')
        if not call_id:
            self.logger.error('No call id!')
            return

        if not self._receiver_callback:
            self.logger.error('No receiver callback set, cannot handle call')
            return

        response = None
        error = None
        try:
            payload = data.get('data', {})
            result = self._receiver_callback(payload)
            if asyncio.iscoroutine(result):
                result = await result
            response = result
        except Exception as e:
            self.logger.exception('Error while handling RPC call')
            error = str(e)
        finally:
            await self._response_listener.post_message({
                'response': response,
                'error': error,
                '__type': 'response',
                '__call_id': str(call_id),
            })

    async def _response_callback(self, _, data):
        call_id = data.get('__call_id')
        if not call_id:
            self.logger.error('Response without call id!')
            return

        fut: asyncio.Future | None = self._response_collection.pop(call_id, None)
        if not fut:
            self.logger.warning(f'Response for unknown or timed-out call_id {call_id}')
            return

        if fut.cancelled():
            # Caller already timed out and cancelled; just drop the response
            return

        error = data.get('error')
        response = data.get('response')

        if error is not None:
            fut.set_exception(RuntimeError(f'RPC error: {error}'))
        else:
            fut.set_result(response)

    async def __call__(self, data, timeout: float | None = None):
        if self._mode != 'client':
            raise Exception("Not running as client")

        call_id = str(uuid.uuid4())

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._response_collection[call_id] = fut

        await self._call_listener.post_message({
            'data': data,
            '__type': 'call',
            '__call_id': call_id,
        })

        try:
            if timeout is not None:
                return await asyncio.wait_for(fut, timeout)
            else:
                return await fut
        except asyncio.TimeoutError:
            # Clean up and propagate
            if not fut.done():
                fut.cancel()
            self._response_collection.pop(call_id, None)
            raise

    async def run_as_server(self, callback_receiver):
        if self._mode:
            raise Exception(f"Already run in mode {self._mode}")
        if not callback_receiver:
            raise ValueError("No callback_receiver")
        self._receiver_callback = callback_receiver
        self._mode = 'server'
        self._call_listener.start()

    async def run_as_client(self):
        if self._mode:
            raise Exception(f"Already run in mode {self._mode}")
        self._mode = 'client'
        self._response_listener.start()
