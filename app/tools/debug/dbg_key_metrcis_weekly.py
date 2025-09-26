import asyncio
import json
import logging
import pickle
from datetime import datetime

from api.vanahaimex import VanaheimixDataSource
from comm.localization.languages import Language
from comm.picture.key_stats_picture import KeyStatsPictureGenerator
from jobs.fetch.key_stats import KeyStatsFetcher
from jobs.user_counter import UserCounterMiddleware
from lib.constants import thor_to_float
from lib.date_utils import DAY
from lib.delegates import INotified
from lib.money import short_dollar, short_rune
from lib.texts import sep
from lib.utils import recursive_asdict
from models.affiliate import AffiliateInterval
from models.key_stats_model import AlertKeyStats, LockedValue
from notify.public.key_metrics_notify import KeyMetricsNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def dbg_load_data_and_save_as_demo_template(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    d = await f.fetch()

    event_as_dict = recursive_asdict(d, add_properties=True, handle_datetime=True)

    call_params = {
        "template_name": "weekly_stats.jinja2",
        "parameters": {
            **event_as_dict,
        }
    }

    sep()
    print(call_params)

    sep()
    json_call_params = json.dumps(call_params, indent=2)
    print(json_call_params)
    sep()

    demo_file = './renderer/demo/weekly_stats.json'
    with open(demo_file, 'w') as f:
        f.write(json_call_params)
        print(f'Saved to {demo_file!r}')


class KeyMetricsSaver(INotified):
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

    f = KeyStatsFetcher(d)
    noter = KeyMetricsNotifier(d)
    f.add_subscriber(noter)
    noter.add_subscriber(d.alert_presenter)

    saver = KeyMetricsSaver()
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


async def old_show_picture(app: LpAppFramework, data):
    # loc = app.deps.loc_man.default
    loc = app.deps.loc_man[Language.ENGLISH]

    pic_gen = KeyStatsPictureGenerator(loc, data)
    pic, name = await pic_gen.get_picture()
    save_and_show_pic(pic, name=name)


async def show_picture(app: LpAppFramework, data):
    loc = app.deps.loc_man[Language.ENGLISH]

    pic, name = await app.deps.alert_presenter.render_key_stats(loc, data)
    save_and_show_pic(pic, name=name)


async def demo_picture(app: LpAppFramework):
    sep()
    print('Start')

    loader = KeyMetricsSaver()
    data = loader.load_data()
    if not data:
        await demo_analyse_and_show(app)
        return


async def debug_locked_value(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    sep()
    curr = await f.get_lock_value()
    print(f'Locked value now: {curr}')
    sep()
    prev = await f.get_lock_value(7 * DAY)
    print(f'Locked value 7 days ago: {prev}')


async def debug_earnings(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    # Earnings
    (
        (curr_total_earnings, curr_block_earnings, curr_organic_fees),
        (prev_total_earnings, prev_block_earnings, prev_organic_fees),
    ) = await f.get_earnings_curr_prev()

    print("Current")
    print(f'{curr_total_earnings = }$, {curr_block_earnings = }$, {curr_organic_fees = }$')
    print(f'{prev_total_earnings = }$, {prev_block_earnings = }$, {prev_organic_fees = }$')


def print_affiliate_table(interval):
    for place, tn in enumerate(interval.thornames[0:20], start=1):
        print(f'#{place:5} {tn.thorname:12} {tn.count:6} '
              f'{short_rune(thor_to_float(tn.volume)):>15} {short_dollar(tn.volume_usd):>15}')


async def dbg_affiliate_top(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)

    affiliates, _, _ = await f.get_top_affiliates()
    for place, collector in enumerate(affiliates, start=1):
        print(f"#{place} | {collector} ")
    # sep()
    # week = result.intervals[0:7]
    # print(len(week))
    # sep()
    # sum_of_int = AffiliateInterval.sum_of_intervals_per_thorname(week).sort_thornames_by_usd_volume()
    # print_affiliate_table(sum_of_int)


async def dbg_vanaheimix(app: LpAppFramework):
    source = VanaheimixDataSource(app.deps.session)
    data = await source.get_affiliate_fees(interval='day', count=14)
    print(data)
    sep()
    print(f'Total intervals: {len(data.intervals)}')
    if data.intervals[0].start_time > data.intervals[-1].start_time:
        print('Intervals are in descending order')
    else:
        print('Intervals are in ascending order')

    prev_week = data.intervals[0:7]
    curr_week = data.intervals[7:]

    prev_week_interval = AffiliateInterval.sum_of_intervals_per_thorname(prev_week).sort_thornames_by_usd_volume()
    curr_week_interval = AffiliateInterval.sum_of_intervals_per_thorname(curr_week).sort_thornames_by_usd_volume()

    sep('Previous')
    print_affiliate_table(prev_week_interval)
    sep('Current')
    print_affiliate_table(curr_week_interval)


async def dbg_recursive_asdict(app: LpAppFramework):
    example = {
        'test': LockedValue(
            date=datetime.now(),
            total_value_bonded=100,
            total_value_bonded_usd=200,
            total_value_locked=150,
            total_value_locked_usd=300,
            total_value_pooled=50,
            total_value_pooled_usd=100,
        )
    }
    print(recursive_asdict(example, add_properties=True, handle_datetime=True))


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        await app.deps.db.get_redis()
        app.deps.user_counter = UserCounterMiddleware(app.deps)

        # await dbg_recursive_asdict(app)
        await demo_analyse_and_show(app)
        # await demo_picture(app)
        # await dbg_load_data_and_save_as_demo_template(app)
        # await debug_locked_value(app)
        # await debug_earnings(app)
        # await dbg_affiliate_top(app)
        # await dbg_vanaheimix(app)


if __name__ == '__main__':
    asyncio.run(main())
