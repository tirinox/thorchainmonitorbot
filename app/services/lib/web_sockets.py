import abc
import asyncio
import socket

import ujson
import websockets

from services.lib.utils import class_logger


class WSClient(abc.ABC):
    @abc.abstractmethod
    async def handle_wss_message(self, reply: dict):
        ...

    async def on_connected(self):
        ...

    def __init__(self, url, reply_timeout=10, ping_timeout=5, sleep_time=5, headers=None):
        self.url = url
        self.reply_timeout = reply_timeout
        self.ping_timeout = ping_timeout
        self.sleep_time = sleep_time
        self.logger = class_logger(self)
        self.headers = headers or {}
        self.ws: websockets.WebSocketClientProtocol = None
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
                                pong = await self.ws.ping()
                                await asyncio.wait_for(pong, timeout=self.ping_timeout)
                                self.logger.debug('Ping OK, keeping connection alive...')
                                continue
                            except Exception:
                                self.logger.debug(
                                    'Ping error - retrying connection in {} sec (Ctrl-C to quit)'.format(
                                        self.sleep_time))
                                await asyncio.sleep(self.sleep_time)
                                break
                        self.logger.debug('Server said > {}'.format(reply))
                        try:
                            message = ujson.loads(reply)
                            await self.handle_wss_message(message)
                        except (ValueError, TypeError, LookupError) as e:
                            self.logger.error(f'Error decoding WebSocket JSON message! {e} Data: {reply[:200]}...')

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
                self.logger.error(f'Other error: {e}')
                await asyncio.sleep(self.sleep_time)

    run = listen_forever
