from typing import NamedTuple

from lib.cooldown import Cooldown
from lib.config import Config
from lib.db import DB
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from .extractor import AchievementsExtractor
from .tracker import AchievementsTracker


class AchievementsSettings(NamedTuple):
    """The `achievements` section of the config; the dashboard shows it too"""
    enabled: bool
    stale_after: float
    cooldown_period: float
    hits_before_cd: int

    COOLDOWN_NAME = 'Achievements:Notification'

    @classmethod
    def load(cls, cfg: Config) -> 'AchievementsSettings':
        return cls(
            enabled=cfg.as_bool('achievements.enabled', True),
            stale_after=cfg.as_interval('achievements.stale_after', '14d'),
            cooldown_period=cfg.as_interval('achievements.cooldown.period', '10m'),
            hits_before_cd=cfg.as_int('achievements.cooldown.hits_before_cd', 3),
        )

    def make_cooldown(self, db: DB) -> Cooldown:
        return Cooldown(db, self.COOLDOWN_NAME, self.cooldown_period, self.hits_before_cd)


class AchievementsNotifier(WithLogger, WithDelegates, INotified):
    async def on_data(self, sender, data):
        try:
            kv_events = await self.extractor.extract_events_by_type(sender, data)

            for event in kv_events:
                if not event:
                    continue

                event = await self.tracker.feed_data(event)
                if event:
                    self.logger.info(f'Achievement event occurred {event}!')

                    if await self.cd.can_do():
                        await self.cd.do()
                        await self.tracker.set_achievement_record(event)
                        await self.pass_data_to_listeners(event)
                    else:
                        # the record is not saved, so it is announced on a later feed
                        self.logger.warning(f'Cooldown is active. Postponing achievement event {event}')

        except Exception as e:
            # we don't let any exception in the Achievements module to break the whole system
            self.logger.exception(f'Error while processing data {type(data)} from {type(sender)}: {e}', exc_info=True)

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        settings = AchievementsSettings.load(deps.cfg)
        self.tracker = AchievementsTracker(deps.db, settings.stale_after)
        self.extractor = AchievementsExtractor(deps)
        self.cd = settings.make_cooldown(deps.db)
