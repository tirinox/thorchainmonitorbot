import asyncio
import logging
from abc import ABC, abstractmethod

from services.config import Config, DB


class BaseFetcher(ABC):
    def __init__(self, cfg: Config, db: DB, sleep_period=60):
        self.cfg = cfg
        self.db = db
        self.name = self.__class__.__qualname__
        self.sleep_period = sleep_period

    @abstractmethod
    async def fetch(self): ...

    @abstractmethod
    async def handle(self, data): ...

    async def run(self):
        await asyncio.sleep(1)
        while True:
            try:
                data = await self.fetch()
                if data:
                    await self.handle(data)

            except Exception as e:
                logging.exception(f"{self.name}: task error: {e}")

            await asyncio.sleep(self.sleep_period)
