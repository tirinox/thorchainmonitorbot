import json
from typing import Optional

from jobs.achievement.ach_list import Achievement
from lib.date_utils import now_ts
from lib.db import DB
from lib.utils import WithLogger


class AchievementsTracker(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db

    @staticmethod
    def key(name, specialization=''):
        if specialization:
            return f'Achievements:{name}:{specialization}'
        else:
            return f'Achievements:{name}'

    @staticmethod
    def meet_threshold(a: Achievement):
        thresholds = a.descriptor.thresholds

        if a.specialization and isinstance(thresholds, dict):
            threshold = thresholds.get(a.specialization)
        else:
            threshold = thresholds

        if threshold is None:
            return True
        else:
            if a.descending:
                return a.value <= threshold
            else:
                return a.value >= threshold

    async def feed_data(self, event: Achievement) -> Optional[Achievement]:
        if not event:
            self.logger.error(f'No event!')
            return

        name, value, descending = event.key, event.value, event.descending
        assert name

        if not value or value <= 0.0:
            self.logger.debug(f'Achievement {name} has invalid ({value}) value! Skip it.')
            return

        if not self.meet_threshold(event):
            return

        current_milestone = event.get_previous_milestone()

        record = await self.get_achievement_record(name, event.specialization)
        if record is None:
            # first time, just write and return
            record = Achievement(
                str(name), int(value), current_milestone,
                timestamp=0,
                specialization=event.specialization,
                descending=descending,
            )
            await self.set_achievement_record(record)
            self.logger.info(f'New achievement record created {record}')
        else:
            # check if we need to update
            if (not event.descending and current_milestone > record.value) or (
                    event.descending and current_milestone < record.value):
                new_record = Achievement(
                    str(name), int(value), current_milestone,
                    timestamp=now_ts(),
                    prev_milestone=record.milestone,
                    previous_ts=record.timestamp,
                    specialization=event.specialization,
                    descending=descending,
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
