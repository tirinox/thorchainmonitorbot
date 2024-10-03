import asyncio

from comm.picture.burn_picture import rune_burn_graph
from lib.date_utils import HOUR, DAY
from notify.public.burn_notify import BurnNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def demo_burn_picture(app: LpAppFramework):
    notifier = BurnNotifier(app.deps)
    points = await notifier.ts.get_last_points(period_sec=7 * DAY, max_points=7 * DAY / HOUR)
    pic, name = await rune_burn_graph(points, app.deps.loc_man.default)
    save_and_show_pic(pic, name)


async def dbg_repopulate(app: LpAppFramework):
    notifier = BurnNotifier(app.deps)
    period = HOUR / 2
    await notifier.erase_and_populate_from_history(period=period, max_points=7 * DAY / period)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await app.deps.last_block_fetcher.run_once()
        # await dbg_repopulate(app)
        await demo_burn_picture(app)


if __name__ == '__main__':
    asyncio.run(run())
