import asyncio
import json
import logging

from lib.db import DB


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
                        if data:
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
