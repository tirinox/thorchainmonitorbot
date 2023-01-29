from services.jobs.achievement.extractor import AchievementsExtractor
from services.jobs.achievement.tracker import AchievementsTracker
from services.lib.cooldown import Cooldown
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class AchievementsNotifier(WithLogger, WithDelegates, INotified):
    async def on_data(self, sender, data):
        try:
            kv_events = await self.extractor.extract_events_by_type(sender, data)

            for event in kv_events:
                event = await self.tracker.feed_data(event)
                if event:
                    self.logger.info(f'Achievement event occurred {event}!')

                    if await self.cd.can_do():
                        await self.cd.do()
                        await self.pass_data_to_listeners(event)
                    else:
                        self.logger.warning(f'Cooldown is active. Skipping achievement event {event}')

        except Exception as e:
            # we don't let any exception in the Achievements module to break the whole system
            self.logger.exception(f'Error while processing data {type(data)} from {type(sender)}: {e}', exc_info=True)

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tracker = AchievementsTracker(deps.db)
        self.extractor = AchievementsExtractor(deps)

        cd = deps.cfg.as_interval('achievement.cooldown.period', '10m')
        max_times = deps.cfg.as_int('achievement.cooldown.hits_before_cd', 3)
        self.cd = Cooldown(self.deps.db, 'Achievements:Notification', cd, max_times)
