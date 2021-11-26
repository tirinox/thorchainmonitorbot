import asyncio
import json
from dataclasses import dataclass
from time import time

from services.lib.date_utils import DAY, now_ts
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


class CooldownBiTriggerOld:
    def __init__(self, db: DB, event_name, cooldown_sec: float = 1e12, switch_cooldown_sec: float = 0.0, default=None,
                 track_last_change_ts=False):
        self.db = db
        self.event_name = event_name
        self.cooldown_sec = cooldown_sec
        self.default = bool(default)
        self.switch_cooldown_sec = switch_cooldown_sec
        self.cd_on = Cooldown(db, f'trigger.{event_name}.on', cooldown_sec)
        self.cd_off = Cooldown(db, f'trigger.{event_name}.off', cooldown_sec)
        self.cd_switch = Cooldown(db, f'trigger.{event_name}.switch', switch_cooldown_sec)
        self.track_last_change_ts = track_last_change_ts
        self._track_last_change_ts_key = f'trigger.{event_name}.last-ts'

    async def turn_on(self) -> bool:
        return await self.turn()

    async def turn_off(self) -> bool:
        return await self.turn(on=False)

    async def get_last_switch_ts(self):
        if self.track_last_change_ts:
            r = await self.db.redis.get(self._track_last_change_ts_key)
            return float(r) if r is not None else 0.0
        else:
            return 0.0

    async def _write_last_switch_ts(self):
        if self.track_last_change_ts:
            await self.db.redis.set(self._track_last_change_ts_key, now_ts())

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

        if result:
            await self._write_last_switch_ts()

        return result


class CooldownBiTrigger:
    def __init__(self, db: DB, event_name,
                 cooldown_on_sec: float = 1e12,
                 cooldown_off_sec: float = 1e12,
                 switch_cooldown_sec: float = 0.0,
                 default=None,
                 track_last_switch_ts=False):
        self.db = db
        self.event_name = event_name
        self.cooldown_on_sec = cooldown_on_sec
        self.cooldown_off_sec = cooldown_off_sec
        self.default = bool(default)
        self.switch_cooldown_sec = switch_cooldown_sec
        self.cd_switch = Cooldown(db, f'trigger.{event_name}.switch', switch_cooldown_sec)
        self.track_last_switch_ts = track_last_switch_ts
        self._key_last_switch_ts = f'trigger.{event_name}.last-switch-ts'
        self._key_last_on_ts = f'trigger.{event_name}.last-on-ts'
        self._key_last_off_ts = f'trigger.{event_name}.last-off-ts'
        self._key_last_state = f'trigger.{event_name}.last-state'

    async def turn_on(self) -> bool:
        return await self.turn()

    async def turn_off(self) -> bool:
        return await self.turn(on=False)

    async def get_state(self) -> bool:
        st = await self.db.redis.get(self._key_last_state)
        return self.default if st is None else bool(int(st))

    async def write_state(self, state, switched):
        r = self.db.redis
        ts = now_ts()
        await asyncio.gather(
            r.set(self._key_last_state, int(state)),
            r.set(self._key_last_on_ts if state else self._key_last_off_ts, ts)
        )
        if self.track_last_switch_ts and switched:
            await r.set(self._key_last_switch_ts, ts)

    async def get_last_switch_ts(self):
        if self.track_last_switch_ts:
            r = await self.db.redis.get(self._key_last_switch_ts)
            return float(r) if r is not None else 0.0
        else:
            raise ValueError('track_last_switch_ts is off')

    async def get_last_update_ts(self, state):
        r = await self.db.redis.get(self._key_last_on_ts if state else self._key_last_off_ts)
        return float(r) if r is not None else 0.0

    async def turn(self, on=True) -> bool:
        has_switch_cd = self.switch_cooldown_sec > 0.0
        if has_switch_cd and not await self.cd_switch.can_do():
            # print(f'{self.event_name}: cd_switch trigger! early')
            return False

        on = bool(on)
        state, last_update_ts = await asyncio.gather(self.get_state(), self.get_last_update_ts(on))
        cd_sec = self.cooldown_on_sec if on else self.cooldown_off_sec

        can_do = last_update_ts + cd_sec < now_ts()
        if can_do:
            switched = on != state
            await self.write_state(on, switched)

            if has_switch_cd:
                await self.cd_switch.do()

            # print(f'{self.event_name}: did')
            return True

        # print(f'{self.event_name}: can_do = false')
        return False
