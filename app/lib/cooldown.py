import asyncio
import json
from dataclasses import dataclass

from lib.date_utils import DAY, now_ts
from lib.db import DB

INFINITE_TIME = 10000 * DAY


@dataclass
class CooldownRecord:
    time: float
    count: int

    def can_do(self, cooldown):
        if not isinstance(self.time, (float, int)):
            return True
        return now_ts() - cooldown > self.time

    def increment_count(self, max_count, cd):
        self.count += 1
        if self.count >= max_count:
            # todo: if waited too long since last event, do not start it again
            self.time = now_ts()
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
        cd.increment_count(self.max_times, self.cooldown)
        await self.write(self.event_name, cd)

    async def clear(self, event_name=None):
        event_name = event_name or self.event_name
        await self.write(event_name, cd=CooldownRecord(0, 0))


class CooldownAlwaysCan(Cooldown):
    def __init__(self):
        # noinspection PyTypeChecker
        super().__init__(None, 'foo', 0.0)

    async def can_do(self):
        return True

    async def do(self):
        pass

    async def clear(self, event_name=None):
        pass


class CooldownBiTrigger:
    def __init__(self, db: DB, event_name,
                 cooldown_on_sec: float = INFINITE_TIME,
                 cooldown_off_sec: float = INFINITE_TIME,
                 switch_cooldown_sec: float = 0.0,
                 default=None,
                 track_last_switch_ts=False):
        self.db = db
        self.event_name = event_name
        self.cooldown_on_sec = cooldown_on_sec
        self.cooldown_off_sec = cooldown_off_sec
        self.default = bool(default)
        self.switch_cooldown_sec = switch_cooldown_sec
        self.cd_switch = Cooldown(db, f'BiStable:{event_name}:switch', switch_cooldown_sec)
        self.track_last_switch_ts = track_last_switch_ts
        self._key_last_switch_ts = f'BiStable:{event_name}.last-switch-ts'
        self._key_last_on_ts = f'BiStable:{event_name}:last-on-ts'
        self._key_last_off_ts = f'BiStable:{event_name}:last-off-ts'
        self._key_last_state = f'BiStable:{event_name}:last-state'

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
            return False

        on = bool(on)
        state, last_update_ts = await asyncio.gather(self.get_state(), self.get_last_update_ts(on))
        cd_sec = self.cooldown_on_sec if on else self.cooldown_off_sec

        switched = on != state
        can_do = last_update_ts + cd_sec < now_ts()

        if switched or can_do:
            await self.write_state(on, switched)

            if has_switch_cd:
                await self.cd_switch.do()
            return True

        return False
