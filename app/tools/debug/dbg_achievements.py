import asyncio
import random

from services.jobs.achievements import AchievementsTracker, AchievementsNotifier, AchievementTest
from services.jobs.fetch.base import BaseFetcher
from services.lib.depcont import DepContainer
from tools.lib.lp_common import LpAppFramework


async def demo_show_notification(app: LpAppFramework):
    ...


class DebugAchievementsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        super().__init__(deps, 1)
        self.deps = deps
        self.limit = 1

    async def fetch(self):
        r = random.randint(1, self.limit)
        self.limit = int(self.limit * random.uniform(1.1, 2.3))
        self.logger.info(f'Generated achievement "test" event with value {r}')
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


async def demo_run_pipeline(app: LpAppFramework):
    ach_fet = DebugAchievementsFetcher(app.deps.db)
    ach_not = AchievementsNotifier(app.deps)
    ach_fet.add_subscriber(ach_not)
    ach_not.add_subscriber(app.deps.alert_presenter)
    await ach_fet.run()


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_debug_logic(app)
        await demo_run_pipeline(app)


if __name__ == '__main__':
    asyncio.run(main())
