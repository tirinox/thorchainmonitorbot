import json
from typing import Optional

from lib.date_utils import now_ts, HOUR, DAY
from lib.db import DB
from lib.logs import WithLogger
from .ach_list import Achievement


class AchievementsTracker(WithLogger):
    # last_seen_ts is rewritten no more often than this, not on every block
    LAST_SEEN_RESOLUTION = HOUR

    def __init__(self, db: DB, stale_after: float = 14 * DAY):
        super().__init__()
        self.db = db
        self.stale_after = stale_after

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
        """
        Returns the new record when the value has crossed a milestone and the achievement must be announced.
        That record is not saved here: the caller saves it with set_achievement_record once it is really sent,
        so an achievement held back by the cooldown is announced on a later feed instead of being lost.
        If the metric was not fed for longer than stale_after (the bot or its source was down),
        a crossed milestone is saved silently, so a restart does not flood the channels with old news.
        An always_fresh metric (the anniversary) is fed only while it is news: it is announced
        after any pause and even on its first feed.
        """
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
        now = now_ts()

        always_fresh = event.descriptor.always_fresh

        record = await self.get_achievement_record(name, event.specialization)
        if record is None and always_fresh:
            # no record to compare with, but it is news anyway
            record = Achievement(str(name), 0, specialization=event.specialization, descending=descending)
        if record is None:
            # first time, just write and return
            record = Achievement(
                str(name), int(value), current_milestone,
                timestamp=0,
                specialization=event.specialization,
                descending=descending,
                last_seen_ts=now,
            )
            await self.set_achievement_record(record)
            self.logger.info(f'New achievement record created {record}')
            return

        crossed = (not descending and current_milestone > record.value) or (
                descending and current_milestone < record.value)
        stale = not always_fresh and now - record.last_seen_ts > self.stale_after

        if not crossed:
            if now - record.last_seen_ts > self.LAST_SEEN_RESOLUTION:
                await self.set_achievement_record(record._replace(last_seen_ts=now))
            return

        new_record = Achievement(
            str(name), int(value), current_milestone,
            timestamp=now,
            prev_milestone=record.milestone,
            previous_ts=record.timestamp,
            specialization=event.specialization,
            descending=descending,
            last_seen_ts=now,
        )
        if stale:
            await self.set_achievement_record(new_record)
            self.logger.warning(f'Achievement {name} was not fed since {record.last_seen_ts}: '
                                f'{new_record} saved silently')
            return

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
