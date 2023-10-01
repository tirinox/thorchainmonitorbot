import abc
import asyncio
import socket

import ujson
import websockets

from services.lib.utils import WithLogger
from services.lib.texts import shorten_text


class WSClient(WithLogger, abc.ABC):
    @abc.abstractmethod
    async def handle_wss_message(self, reply: dict):
        ...

    async def on_connected(self):
        ...

    def __init__(self, url, reply_timeout=13.3, ping_timeout=5, sleep_time=5, headers=None):
        self.url = url
        self.reply_timeout = reply_timeout
        self.ping_timeout = ping_timeout
        self.sleep_time = sleep_time

        self.headers = headers or {}
        self.ws: websockets.WebSocketClientProtocol = None
        self.exception_safe = True
        super().__init__()

    async def send_message(self, message):
        await self.ws.send(ujson.dumps(message))

    async def listen_forever(self):
        while True:
            self.logger.info(f'Creating new connection... to {self.url}')
            try:
                async with websockets.connect(self.url, extra_headers=self.headers) as self.ws:
                    await self.on_connected()
                    while True:
                        # listener loop
                        try:
                            reply = await asyncio.wait_for(self.ws.recv(), timeout=self.reply_timeout)
                        except (asyncio.TimeoutError, websockets.ConnectionClosed):
                            try:
                                if self.ping_timeout:
                                    pong = await self.ws.ping()
                                    await asyncio.wait_for(pong, timeout=self.ping_timeout)
                                    self.logger.info('Ping OK, keeping connection alive...')
                                    continue
                                else:
                                    self.logger.warn('Reconnect on timeout!')
                                    break
                            except Exception:
                                self.logger.info(
                                    'Ping error - retrying connection in {} sec (Ctrl-C to quit)'.format(
                                        self.sleep_time))
                                await asyncio.sleep(self.sleep_time)
                                break
                        self.logger.debug('Server said > {}'.format(reply))
                        try:
                            message = ujson.loads(reply)
                            await self.handle_wss_message(message)
                        except (ValueError, TypeError, LookupError) as e:
                            r = shorten_text(reply, 256)
                            self.logger.error(f'Error decoding WebSocket JSON message! {e!r} Data: "{r}"')
                        except Exception as e:
                            if not self.exception_safe:
                                raise
                            else:
                                self.logger.error(f'Other error: {e!r}')

            except socket.gaierror:
                self.logger.warn(f'Socket error - retrying connection in {self.sleep_time} sec ')
                await asyncio.sleep(self.sleep_time)
                continue
            except ConnectionRefusedError:
                self.logger.error('Nobody seems to listen to this endpoint. Please check the URL.')
                self.logger.debug(f'Retrying connection in {self.sleep_time}')
                await asyncio.sleep(self.sleep_time)
                continue
            except Exception as e:
                if not self.exception_safe:
                    raise
                else:
                    self.logger.error(f'Other error: {e!r}')
                    await asyncio.sleep(self.sleep_time)

    run = listen_forever
