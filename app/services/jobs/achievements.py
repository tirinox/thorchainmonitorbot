import json
import math
from enum import Enum
from typing import NamedTuple, Optional

from services.lib.date_utils import now_ts
from services.lib.db import DB
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.net_stats import NetworkStats


class Achievement(Enum):
    DAU = 'dau'
    MAU = 'mau'
    WALLET_COUNT = 'wallet_count'
    DAILY_TX_COUNT = 'daily_tx_count'
    DAILY_VOLUME = 'daily_volume'


class Milestones:
    MILESTONE_DEFAULT_PROGRESSION = [1, 2, 5]

    def __init__(self, progression=None):
        self.progression = progression or self.MILESTONE_DEFAULT_PROGRESSION

    def milestone_nearest(self, x, before: bool):
        progress = self.progression
        x = int(x)
        if x <= 0:
            return self.progression[0]

        mag = 10 ** int(math.log10(x))
        if before:
            delta = -1
            mag *= 10
        else:
            delta = 1
        i = 0

        while True:
            step = progress[i]
            y = step * mag
            if before and x >= y:
                return y
            if not before and x < y:
                return y
            i += delta
            if i < 0:
                i = len(progress) - 1
                mag //= 10
            elif i >= len(progress):
                i = 0
                mag *= 10

    def next(self, x):
        return self.milestone_nearest(x, before=False)

    def previous(self, x):
        return self.milestone_nearest(x, before=True)


class AchievementRecord(NamedTuple):
    key: str
    value: int
    previous_value: int
    last_ts: float


class EventAchievement(NamedTuple):
    achievement: AchievementRecord


class AchievementsTracker(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.milestones = Milestones()

    def key(self, name):
        return f'Achievements:{name}'

    async def feed_data(self, name: Achievement, value: int) -> Optional[EventAchievement]:
        assert name
        record = await self.get_achievement_record(name)
        if record is None:
            record = AchievementRecord(str(name), value, 0, now_ts())
            await self.set_achievement_record(record)
            self.logger.info(f'New achievement record created {record}')
        else:
            value_milestone = self.milestones.previous(value)
            if value_milestone > record.value:
                record = AchievementRecord(str(name), value_milestone, record.value, now_ts())
                await self.set_achievement_record(record)
                self.logger.info(f'Achievement record updated {record}')
                return EventAchievement(record)

    async def get_achievement_record(self, key) -> Optional[AchievementRecord]:
        key = self.key(key)
        data = await self.db.redis.get(key)
        try:
            return AchievementRecord(**json.loads(data))
        except (TypeError, json.JSONDecodeError):
            return None

    async def set_achievement_record(self, record: AchievementRecord):
        key = self.key(record.key)
        await self.db.redis.set(key, json.dumps(record._asdict()))


class AchievementsNotifier(WithLogger, WithDelegates, INotified):
    async def on_data(self, sender, data):
        if isinstance(data, NetworkStats):
            await self.on_network_stats(data)
        else:
            self.logger.warning(f'Unknown data type {type(data)}. Dont know how to handle it.')

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tracker = AchievementsTracker(deps.db)

    async def on_network_stats(self, data: NetworkStats):
        achievements = [
            (Achievement.DAU, data.users_daily),
            (Achievement.MAU, data.users_monthly),
            # todo: add more
        ]

        for key, value in achievements:
            event = await self.tracker.feed_data(key, value)
            if event:
                await self.pass_data_to_listeners(event)
