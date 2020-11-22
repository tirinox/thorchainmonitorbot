from time import time

from services.lib.db import DB


class CooldownTracker:
    def __init__(self, db: DB):
        self.db = db

    @staticmethod
    def get_key(name):
        return f"cd_evt:{name}"

    async def can_do(self, event_name, cooldown):
        last_time = await self.db.redis.get(self.get_key(event_name))
        if last_time is None:
            return True
        last_time = float(last_time)
        return time() - cooldown > last_time

    async def do(self, event_name):
        await self.db.redis.set(self.get_key(event_name), time())

    async def clear(self, event_name):
        await self.db.redis.set(self.get_key(event_name), 0.0)
