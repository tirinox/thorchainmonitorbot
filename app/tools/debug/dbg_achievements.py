import asyncio

from services.jobs.achievements import AchievementsTracker
from tools.lib.lp_common import LpAppFramework


async def demo_show_notification(app: LpAppFramework):
    ...


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


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        await demo_debug_logic(app)


if __name__ == '__main__':
    asyncio.run(main())
