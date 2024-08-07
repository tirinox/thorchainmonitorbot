import asyncio
import logging
import pickle

from localization.languages import Language
from services.dialog.picture.key_stats_picture import KeyStatsPictureGenerator
from services.jobs.fetch.flipside import FlipSideConnector, FSList
from services.jobs.fetch.flipside.urls import *
from services.jobs.fetch.key_stats import KeyStatsFetcher
from services.jobs.user_counter import UserCounterMiddleware
from services.jobs.volume_recorder import TxCountRecorder, VolumeRecorder
from services.lib.date_utils import DAY
from services.lib.delegates import INotified
from services.lib.texts import sep
from services.models.flipside import FSAffiliateCollectors, FSFees, FSSwapVolume, FSSwapCount, \
    FSLockedValue, AlertKeyStats
from services.notify.types.key_metrics_notify import KeyMetricsNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def demo_load(app: LpAppFramework):
    await app.deps.last_block_fetcher.run_once()
    f = KeyStatsFetcher(app.deps)
    d = await f.fetch()
    print(d)


async def demo_load_single_fs_list(app: LpAppFramework):
    fs = FlipSideConnector(app.deps.session, app.deps.cfg.flipside.api_key)

    tasks = [
        (FS_LATEST_EARNINGS_URL, FSFees),
        (FS_LATEST_SWAP_VOL_URL, FSSwapVolume),
        (FS_LATEST_SWAP_AFF_FEE_URL, FSAffiliateCollectors),
        (FS_LATEST_LOCKED_RUNE_URL, FSLockedValue),
        (FS_LATEST_SWAP_COUNT_URL, FSSwapCount)
    ]

    async def load_one(url, cls):
        data = await fs.request_daily_series_v2(url, cls)
        sep(str(cls))
        print(f'Loaded {cls.__name__} from {url}')
        print(data)
        sep()
        return data

    lists = [await load_one(url, cls) for url, cls in tasks]

    combined_list = FSList.combine(*lists)
    print(combined_list)
    sep()


class FlipSideSaver(INotified):
    DEFAULT_FILENAME = '../temp/fs_key_metrics_v7.pickle'

    def __init__(self, filename=DEFAULT_FILENAME) -> None:
        super().__init__()
        self.filename = filename

    async def on_data(self, sender, data):
        # result, fresh_pools, old_pools = data
        # result: FSList
        with open(self.filename, 'wb') as f:
            pickle.dump(data, f)
            print(f'DATA SAVED to {self.filename}')

    def load_data(self):
        try:
            with open(self.filename, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass


async def demo_analyse_and_show(app: LpAppFramework):
    d = app.deps
    d.volume_recorder = VolumeRecorder(d)
    # volume_filler.add_subscriber(d.volume_recorder)

    d.tx_count_recorder = TxCountRecorder(d)
    # volume_filler.add_subscriber(d.tx_count_recorder)

    f = KeyStatsFetcher(d)
    noter = KeyMetricsNotifier(d)
    f.add_subscriber(noter)
    noter.add_subscriber(d.alert_presenter)

    saver = FlipSideSaver()
    f.add_subscriber(saver)

    # await f.run_once()
    result: AlertKeyStats = await f.fetch()
    sep('Weekly stats')
    print(result)
    sep('Swap vol: current')
    print(result.current.swap_vol)
    sep('Swap count: current')
    print(result.current.swapper_count)
    sep('Swap vol: previous')
    print(result.previous.swap_vol)
    sep('Swap count: previous')
    print(result.previous.swapper_count)

    await show_picture(app, result)

    await asyncio.sleep(5)  # let them send the picture


async def show_picture(app: LpAppFramework, data):
    # loc = app.deps.loc_man.default
    loc = app.deps.loc_man[Language.ENGLISH]

    pic_gen = KeyStatsPictureGenerator(loc, data)
    pic, name = await pic_gen.get_picture()
    save_and_show_pic(pic, name=name)


async def demo_picture(app: LpAppFramework):
    sep()
    print('Start')

    loader = FlipSideSaver()
    data = loader.load_data()
    if not data:
        await demo_analyse_and_show(app)
        return


async def debug_locked_value(app: LpAppFramework):
    await app.deps.last_block_fetcher.run_once()
    f = KeyStatsFetcher(app.deps)
    sep()
    curr = await f.get_lock_value()
    print(f'Locked value now: {curr}')
    sep()
    prev = await f.get_lock_value(7 * DAY)
    print(f'Locked value 7 days ago: {prev}')


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        lp_app.deps.user_counter = UserCounterMiddleware(lp_app.deps)
        await lp_app.deps.last_block_fetcher.run_once()
        # await lp_app.prepare(brief=True)

        # await demo_analyse_and_show(lp_app)
        await demo_picture(lp_app)
        # await demo_new_flipside_sql(lp_app)
        # await demo_load(lp_app)
        # await demo_new_flipside_swap_routes(lp_app)
        # await demo_load_single_fs_list(lp_app)
        # await debug_locked_value(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
