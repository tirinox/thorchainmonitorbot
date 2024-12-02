import asyncio
import json
from pprint import pprint

from comm.picture.burn_picture import rune_burn_graph
from lib.date_utils import HOUR, DAY
from lib.texts import sep
from notify.public.burn_notify import BurnNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def demo_burn_picture(app: LpAppFramework, notifier):
    points = await notifier.ts.get_last_points(period_sec=7 * DAY, max_points=7 * DAY / HOUR)
    pic, name = await rune_burn_graph(points, app.deps.loc_man.default)
    save_and_show_pic(pic, name)

    last_max_supply = await notifier.ts.get_last_value('max_supply')
    print(f'Last max supply: {last_max_supply}')


async def demo_last_burn_event(app: LpAppFramework, notifier):
    event = await notifier.get_event()
    pprint(event._asdict())
    sep()
    print(json.dumps(event._asdict(), indent=2))
    sep()

    await app.deps.alert_presenter.on_data(None, event)
    await asyncio.sleep(10)


async def dbg_repopulate(app: LpAppFramework, notifier):
    period = HOUR / 2
    await notifier.erase_and_populate_from_history(period=period, max_points=7 * DAY / period)


async def run():
    app = LpAppFramework(log_level='INFO')
    async with app(brief=True):
        await app.deps.last_block_fetcher.run_once()
        await app.deps.mimir_const_fetcher.run_once()
        await app.deps.pool_fetcher.run_once()
        notifier = BurnNotifier(app.deps)
        # await dbg_repopulate(app, notifier)
        # await demo_burn_picture(app, notifier)
        await demo_last_burn_event(app, notifier)


if __name__ == '__main__':
    asyncio.run(run())
