import asyncio
import random

from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.dialog.picture.achievement_picture import AchievementPictureGenerator
from services.jobs.achievements import AchievementsTracker, AchievementsNotifier, AchievementTest, Achievement, \
    AchievementRecord, EventAchievement
from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import now_ts, DAY
from services.lib.depcont import DepContainer
from services.lib.texts import sep
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def demo_show_notification(app: LpAppFramework):
    ...


class DebugAchievementsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        super().__init__(deps, 1)
        self.deps = deps
        self.limit = 3

    async def fetch(self):
        r = random.randint(1, self.limit)
        self.limit = int(self.limit * random.uniform(1.1, 1.5))
        self.logger.info(f'Generated achievement "test" event with value {r} ({self.limit = })')
        return AchievementTest(r)


async def demo_debug_logic(app: LpAppFramework):
    at: AchievementsTracker = AchievementsTracker(app.deps.db)
    while True:
        event = input('Enter event: ')
        if not event:
            break
        event, value = event.split()
        value = int(value)
        r = await at.feed_data(event, value)
        print(f'Event: {r}')


async def demo_achievements_picture():
    # subject to change
    rec = AchievementRecord(Achievement.ANNIVERSARY, 3, 3, now_ts(), 2, now_ts() - random.randint(1, int(100 * DAY)))

    loc = AchievementsEnglishLocalization()
    gen = AchievementPictureGenerator(loc, rec)
    pic, pic_name = await gen.get_picture()
    save_and_show_pic(pic, name=pic_name)

    text = loc.notification_achievement_unlocked(EventAchievement(rec))
    sep()
    print(text)
    sep()

async def demo_run_pipeline(app: LpAppFramework):
    ach_fet = DebugAchievementsFetcher(app.deps.db)
    ach_not = AchievementsNotifier(app.deps)
    ach_fet.add_subscriber(ach_not)
    ach_not.add_subscriber(app.deps.alert_presenter)

    await ach_not.tracker.delete_achievement_record(Achievement.TEST)

    await ach_fet.run()


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_debug_logic(app)
        # await demo_run_pipeline(app)

        await demo_achievements_picture()


if __name__ == '__main__':
    asyncio.run(main())
