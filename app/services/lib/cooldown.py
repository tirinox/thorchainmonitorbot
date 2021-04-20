import json
from dataclasses import dataclass
from time import time

from services.lib.db import DB


class CooldownSingle:
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


@dataclass
class CooldownRecord:
    time: float
    count: int

    def can_do(self, cooldown):
        if not isinstance(self.time, (float, int)):
            return True
        return time() - cooldown > self.time

    def increment_count(self, max_count):
        self.count += 1
        if self.count >= max_count:
            self.time = time()
            self.count = 0


class Cooldown:
    def __init__(self, db: DB, event_name, cooldown, max_times=1):
        self.db = db
        self.event_name = event_name
        self.cooldown = cooldown
        self.max_times = max_times

    @staticmethod
    def get_key(name):
        return f"cooldown:{name}"

    async def read(self, event_name):
        data = await self.db.redis.get(self.get_key(event_name))
        try:
            return CooldownRecord(**json.loads(data))
        except (TypeError, json.decoder.JSONDecodeError):
            return CooldownRecord(0.0, 0)

    async def write(self, event_name, cd: CooldownRecord):
        await self.db.redis.set(self.get_key(event_name),
                                json.dumps(cd.__dict__))

    async def can_do(self):
        cd = await self.read(self.event_name)
        return cd.can_do(self.cooldown)

    async def do(self):
        cd = await self.read(self.event_name)
        if not cd.can_do(self.cooldown):
            return
        cd.increment_count(self.max_times)
        await self.write(self.event_name, cd)

    async def clear(self, event_name=None):
        event_name = event_name or self.event_name
        await self.write(event_name, cd=CooldownRecord(0, 0))
