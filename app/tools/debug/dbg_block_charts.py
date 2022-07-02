import asyncio

from services.lib.telegram import TG_TEST_USER

from localization.manager import BaseLocalization, RussianLocalization
from services.dialog.picture.block_height_picture import block_speed_chart
from services.jobs.fetch.last_block import LastBlockFetcher
from services.lib.constants import THOR_BLOCKS_PER_MINUTE
from services.lib.date_utils import DAY
from services.lib.delegates import INotified
from services.notify.types.block_notify import BlockHeightNotifier
from tools.lib.lp_common import LpAppFramework


def my_test_smart_block_time_estimator():
    pts = [
        (1, 1),
        (2, 2),
        (3, 3),
        (22, 3),
        (25, 4),
        (26, 5),
        (30, 6),
        (45, 7),
        (60, 8),
        (66, 9)
    ]
    r = BlockHeightNotifier.smart_block_time_estimator(pts, 10)
    print(f'{pts = }:\nResult: {r}')

    pts = [
        (v, v * v) for v in range(51)
    ]
    r = BlockHeightNotifier.smart_block_time_estimator(pts, 10)
    print(f'{pts = }:\nResult: {r}')


class FooSubscribed(INotified):
    def __init__(self, block_not: BlockHeightNotifier, loc):
        self.block_not = block_not
        self.loc = loc

    async def on_data(self, sender, data):
        chart = await self.block_not.get_block_time_chart(2 * DAY, convert_to_blocks_per_minute=True)
        pic_chart = await block_speed_chart(chart, self.loc, normal_bpm=10, time_scale_mode='time')
        pic_chart.show()


async def my_test_block_fetch(app: LpAppFramework):
    async with app:
        lbf = LastBlockFetcher(app.deps)
        block_not = BlockHeightNotifier(app.deps)
        lbf.subscribe(block_not)
        lbf.subscribe(FooSubscribed(block_not, app.deps.loc_man.default))
        await lbf.run()


async def my_test_tg_message(app: LpAppFramework):
    block_not = BlockHeightNotifier(app.deps)

    for loc in (RussianLocalization(app.deps.cfg), app.deps.loc_man.default,):
        loc: BaseLocalization

        text = loc.notification_text_block_stuck(True, 10000)
        # await app.send_test_tg_message(text)

        points = await block_not.get_block_time_chart(DAY * 2, convert_to_blocks_per_minute=True)
        chart = await block_speed_chart(points, loc, normal_bpm=THOR_BLOCKS_PER_MINUTE, time_scale_mode='time')
        await app.deps.telegram_bot.bot.send_photo(TG_TEST_USER, chart, caption=text)

        await app.send_test_tg_message(loc.notification_text_block_stuck(False, 10000))


async def main():
    # my_test_smart_block_time_estimator()
    app = LpAppFramework()
    async with app:
        await my_test_tg_message(app)
        # await my_test_block_fetch(app)


if __name__ == "__main__":
    # test_upd()
    asyncio.run(main())
