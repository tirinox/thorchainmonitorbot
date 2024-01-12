import asyncio
import logging
import pickle

from localization.languages import Language
from services.dialog.picture.key_stats_picture import KeyStatsPictureGenerator
from services.jobs.fetch.key_stats import KeyStatsFetcher
from services.lib.delegates import INotified
from services.lib.texts import sep
from services.notify.types.key_metrics_notify import KeyMetricsNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def demo_load(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    await f.fetch()


class FlipSideSaver(INotified):
    DEFAULT_FILENAME = '../temp/fs_key_metrics_4.pickle'

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


async def demo_analyse(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    noter = KeyMetricsNotifier(app.deps)
    f.add_subscriber(noter)
    noter.add_subscriber(app.deps.alert_presenter)

    saver = FlipSideSaver()
    f.add_subscriber(saver)

    await f.run_once()
    await asyncio.sleep(5)  # let them send the picture


async def demo_picture(app: LpAppFramework):
    sep()
    print('Start')

    loader = FlipSideSaver()
    data = loader.load_data()
    if not data:
        await demo_analyse(app)
        data = loader.load_data()

    sep()
    print('Data loaded')

    # loc = app.deps.loc_man.default
    loc = app.deps.loc_man[Language.RUSSIAN]

    pic_gen = KeyStatsPictureGenerator(loc, data)
    pic, name = await pic_gen.get_picture()
    save_and_show_pic(pic, name=name)


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        # await lp_app.prepare(brief=True)

        await demo_analyse(lp_app)
        await demo_picture(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
