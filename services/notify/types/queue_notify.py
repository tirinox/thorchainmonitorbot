import asyncio

from localization import LocalizationManager
from services.config import Config, DB
from services.fetch.queue import QueueFetcher, QueueInfo
from services.cooldown import CooldownTracker
from services.notify.broadcast import Broadcaster


class QueueNotifier(QueueFetcher):
    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, loc_man: LocalizationManager):
        super().__init__(cfg, db)
        self.broadcaster = broadcaster
        self.loc_man = loc_man
        self.cooldown_tracker = CooldownTracker(db)
        self.cooldown = 60 * 60  # 1 hour
        self.steps = [
            50, 10, 0
        ]

    async def notify(self, item_type, step, value):
        self.logger.warn(f'Queue {item_type} is {value}!!!')

    async def handle_entry(self, item_type, value):
        for step in self.steps:
            if value >= step:
                k = f'q:{item_type}:{step}'
                if await self.cooldown_tracker.can_do(k, self.cooldown):
                    await self.notify(item_type, step, value)
                    await self.cooldown_tracker.do(k)
                    break

    async def handle(self, data: QueueInfo):
        await asyncio.gather(self.handle_entry('swap', data.swap),
                             self.handle_entry('outbound', data.outbound))
