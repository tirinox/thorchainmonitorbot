import asyncio
import logging
from abc import ABC, abstractmethod

from aiohttp import ClientSession

from services.config import Config
from services.db import DB


class INotified(ABC):
    @abstractmethod
    async def on_data(self, data): ...

    async def on_error(self, e):
        ...


class BaseFetcher(ABC):
    def __init__(self, cfg: Config, db: DB, session: ClientSession, sleep_period=60, delegate: INotified = None):
        self.cfg = cfg
        self.db = db
        self.session = session
        self.delegate = delegate
        self.name = self.__class__.__qualname__
        self.sleep_period = sleep_period
        self.logger = logging.getLogger(f'{self.__class__.__name__}')

    @abstractmethod
    async def fetch(self):
        ...

    async def handle_error(self, e):
        await self.delegate.on_error(e)

    async def run(self):
        await asyncio.sleep(1)
        while True:
            try:
                data = await self.fetch()
                if data:
                    await self.delegate.on_data(data)

            except Exception as e:
                logging.exception(f"task error: {e}")

                try:
                    await self.handle_error(e)
                except Exception as e:
                    logging.exception(f"task error while handling on_error: {e}")

            await asyncio.sleep(self.sleep_period)
