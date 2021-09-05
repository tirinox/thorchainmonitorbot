import asyncio
import json
from dataclasses import dataclass
from time import time

from services.lib.date_utils import DAY
from services.lib.db import DB

INFINITE_TIME = 10000 * DAY


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
    def __init__(self, db: DB, event_name, cooldown: float, max_times=1):
        self.db = db
        self.event_name = event_name
        self.cooldown = cooldown
        self.max_times = max_times
        assert isinstance(cooldown, (int, float))

    @staticmethod
    def get_key(name):
        return f"cooldown:{name}"

    async def read(self, event_name):
        redis = await self.db.get_redis()
        data = await redis.get(self.get_key(event_name))
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


class CooldownBiTrigger:
    def __init__(self, db: DB, event_name, cooldown_sec: float, switch_cooldown_sec: float = 0.0, default=None):
        self.db = db
        self.event_name = event_name
        self.cooldown_sec = cooldown_sec
        self.default = bool(default)
        self.switch_cooldown_sec = switch_cooldown_sec
        self.cd_on = Cooldown(db, f'trigger.{event_name}.on', cooldown_sec)
        self.cd_off = Cooldown(db, f'trigger.{event_name}.off', cooldown_sec)
        self.cd_switch = Cooldown(db, f'trigger.{event_name}.switch', switch_cooldown_sec)

    async def turn_on(self) -> bool:
        return await self.turn()

    async def turn_off(self) -> bool:
        return await self.turn(on=False)

    async def turn(self, on=True) -> bool:
        has_switch_cd = self.switch_cooldown_sec > 0.0

        if has_switch_cd and not await self.cd_switch.can_do():
            return False

        result = False

        can_on, can_off = await asyncio.gather(self.cd_on.can_do(), self.cd_off.can_do())

        if not can_on and not can_off and self.default is not None:
            # 1st time! using Default
            default = bool(self.default)
            which = self.cd_on if default else self.cd_off
            await which.do()
            result = on != default
            """
             DEFAULT = True
                1. On = True (== default) => turn it on! 
                    FALSE (it is already ON by default)
                2. On = False (!= default) => turn it off!
                    TRUE
            """

        elif on and can_on:
            await asyncio.gather(self.cd_on.do(), self.cd_off.clear())
            result = True
        elif not on and can_off:
            await asyncio.gather(self.cd_off.do(), self.cd_on.clear())
            result = True

        if result and has_switch_cd:
            await self.cd_switch.do()

        return result
