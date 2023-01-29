import json
from typing import Optional

from services.jobs.achievement.ach_list import GROUP_MINIMALS, GROUP_EVERY_1, Achievement
from services.jobs.achievement.milestones import Milestones
from services.lib.date_utils import now_ts
from services.lib.db import DB
from services.lib.utils import WithLogger


class AchievementsTracker(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.milestones = Milestones()
        self.milestones_every = Milestones(list(range(1, 10)))

    @staticmethod
    def key(name, specialization=''):
        if specialization:
            return f'Achievements:{name}:{specialization}'
        else:
            return f'Achievements:{name}'

    @staticmethod
    def get_minimum(key):
        return GROUP_MINIMALS.get(key, 1)

    def get_previous_milestone(self, key, value):
        if key in GROUP_EVERY_1:
            v = self.milestones_every.previous(value)
        else:
            v = self.milestones.previous(value)

        return v

    async def feed_data(self, event: Achievement) -> Optional[Achievement]:
        name, value = event.key, event.value
        assert name

        if value < self.get_minimum(name):
            return None

        record = await self.get_achievement_record(name, event.specialization)
        current_milestone = self.get_previous_milestone(name, value)
        if record is None:
            # first time, just write and return
            record = Achievement(
                str(name), int(value), current_milestone,
                timestamp=0,
                specialization=event.specialization
            )
            await self.set_achievement_record(record)
            self.logger.info(f'New achievement record created {record}')
        else:
            # check if we need to update
            if current_milestone > record.value:
                new_record = Achievement(
                    str(name), int(value), current_milestone,
                    timestamp=now_ts(),
                    prev_milestone=record.milestone,
                    previous_ts=record.timestamp,
                    specialization=event.specialization,
                )
                await self.set_achievement_record(new_record)
                self.logger.info(f'Achievement record updated {new_record}')
                return new_record

    async def get_achievement_record(self, key, specialization) -> Optional[Achievement]:
        key = self.key(key, specialization)
        data = await self.db.redis.get(key)
        try:
            return Achievement(**json.loads(data))
        except (TypeError, json.JSONDecodeError):
            return None

    async def set_achievement_record(self, record: Achievement):
        key = self.key(record.key, record.specialization)
        await self.db.redis.set(key, json.dumps(record._asdict()))

    async def delete_achievement_record(self, key, specialization=''):
        key = self.key(key, specialization)
        await self.db.redis.delete(key)
