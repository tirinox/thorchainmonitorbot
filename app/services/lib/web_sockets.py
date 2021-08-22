import asyncio
import socket

import websockets

from services.lib.utils import class_logger


class WSClient:
    def __init__(self, url, **kwargs):
        self.url = url
        self.reply_timeout = kwargs.get('reply_timeout') or 10
        self.ping_timeout = kwargs.get('ping_timeout') or 5
        self.sleep_time = kwargs.get('sleep_time') or 5
        self.callback = kwargs.get('callback')
        self.logger = class_logger(self)

    async def listen_forever(self):
        while True:
            self.logger.debug('Creating new connection...')
            try:
                async with websockets.connect(self.url) as ws:
                    while True:
                        # listener loop
                        try:
                            reply = await asyncio.wait_for(ws.recv(), timeout=self.reply_timeout)
                        except (asyncio.TimeoutError, websockets.ConnectionClosed):
                            try:
                                pong = await ws.ping()
                                await asyncio.wait_for(pong, timeout=self.ping_timeout)
                                self.logger.debug('Ping OK, keeping connection alive...')
                                continue
                            except:
                                self.logger.debug(
                                    'Ping error - retrying connection in {} sec (Ctrl-C to quit)'.format(self.sleep_time))
                                await asyncio.sleep(self.sleep_time)
                                break
                        self.logger.debug('Server said > {}'.format(reply))
                        if self.callback:
                            self.callback(reply)
            except socket.gaierror:
                self.logger.debug(
                    'Socket error - retrying connection in {} sec (Ctrl-C to quit)'.format(self.sleep_time))
                await asyncio.sleep(self.sleep_time)
                continue
            except ConnectionRefusedError:
                self.logger.debug('Nobody seems to listen to this endpoint. Please check the URL.')
                self.logger.debug('Retrying connection in {} sec (Ctrl-C to quit)'.format(self.sleep_time))
                await asyncio.sleep(self.sleep_time)
                continue