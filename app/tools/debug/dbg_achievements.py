import asyncio
import datetime
import os
import random

from comm.localization.achievements.ach_eng import AchievementsEnglishLocalization
from comm.localization.achievements.ach_rus import AchievementsRussianLocalization
from comm.localization.achievements.common import AchievementsLocalizationBase
from comm.localization.languages import Language
from comm.picture.achievement_card import build_achievement_card, achievement_card_filename, \
    ACHIEVEMENT_TEMPLATE
from comm.telegram.telegram import TG_TEST_USER
from jobs.achievement.ach_list import Achievement, EventTestAchievement, A, AchievementDescription, \
    ACHIEVEMENT_DESC_MAP, META_KEY_SPEC
from jobs.achievement.milestones import Milestones
from jobs.achievement.notifier import AchievementsNotifier
from jobs.achievement.tracker import AchievementsTracker
from jobs.fetch.base import BaseFetcher
from lib.date_utils import now_ts, DAY
from lib.depcont import DepContainer
from lib.draw_utils import img_to_bio
from lib.texts import sep
from models.price import RuneMarketInfo
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


class DebugAchievementsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, specialization: str = '', descending=False):
        super().__init__(deps, 1)
        self.deps = deps
        self.descending = descending
        self.specialization = specialization
        self.current = 300 if descending else 3

    async def fetch(self):
        old = self.current
        if self.descending:
            self.current *= random.uniform(0.7, 0.99)
            self.current = max(1, int(self.current))
        else:
            self.current = int(self.current * random.uniform(1.1, 1.5))

        self.logger.info(f'Generated achievement "test": ({old} -> {self.current} new!)')
        return EventTestAchievement(self.current, self.specialization, self.descending)


class DebugAchievementRank(BaseFetcher):
    def __init__(self, deps: DepContainer, sleep_period=1, specialization='', start=44):
        super().__init__(deps, sleep_period)
        self.rank = start
        self.specialization = specialization

    async def fetch(self):
        self.rank = max(1, self.rank - random.randint(1, 4))
        print('❤️❤️❤️RUNE RANK!!!: ', self.rank)
        return RuneMarketInfo(
            rank=self.rank,
            pools={}
        )


async def demo_debug_logic(app: LpAppFramework):
    at: AchievementsTracker = AchievementsTracker(app.deps.db)
    while True:
        event = input('Enter event: ')
        if not event:
            break
        event, value = event.split()
        value = int(value)
        r = await at.feed_data(Achievement(event, value))
        if r:
            await at.set_achievement_record(r)
        print(f'Event: {r}')


def random_achievement():
    milestones = Milestones()
    value = random.randint(1, random.randint(1, 1_000_000_000))
    milestone = milestones.previous(value)

    random_achievement_key = random.choice(ACHIEVEMENT_DESC_MAP).key
    rec = Achievement(random_achievement_key, value,
                      milestone, now_ts(),
                      2, now_ts() - random.randint(1, int(100 * DAY)))
    return rec


async def render_achievement_card(app: LpAppFramework, rec: Achievement, loc: AchievementsLocalizationBase,
                                  show=True):
    # needs the HTML renderer running (make renderer-dev)
    parameters = build_achievement_card(rec, loc)
    pic = await app.deps.alert_presenter.renderer.render(ACHIEVEMENT_TEMPLATE, parameters)
    save_and_show_pic(pic, name=f'a/{type(loc).__name__}-{achievement_card_filename(rec)}', show=show)
    return pic


async def demo_achievements_picture(app: LpAppFramework,
                                    lang=None, a=None, v=None, milestone=None, descending=False,
                                    spec='', send_to_tg=False):
    # rec = random_achievement()
    v = v or 501_344_119
    milestone = milestone or 500_000_000
    prev_milestone = 200_000_000
    previous_ts = now_ts() - random.randint(1, 30) * DAY
    rec = Achievement(a or A.MARKET_CAP_USD, v, milestone, now_ts(), prev_milestone,
                      previous_ts, spec, descending=descending)
    lang = lang or Language.ENGLISH

    loc = AchievementsRussianLocalization() if lang == Language.RUSSIAN else AchievementsEnglishLocalization()
    pic = await render_achievement_card(app, rec, loc)

    text = loc.notification_achievement_unlocked(rec)
    sep()
    print(text)
    sep()

    if send_to_tg:
        d: DepContainer = app.deps
        await d.telegram_bot.bot.send_photo(
            TG_TEST_USER, img_to_bio(pic, '1.png'), caption=text,
        )
        await asyncio.sleep(1.0)


async def demo_all_achievements(app: LpAppFramework):
    loc_en = AchievementsEnglishLocalization()
    loc_ru = AchievementsRussianLocalization()

    os.makedirs('../temp/a', exist_ok=True)
    show = False

    for loc in [loc_en, loc_ru]:
        print(loc.__class__.__name__)

        for ach_key in ACHIEVEMENT_DESC_MAP:
            if ach_key == A.ANNIVERSARY:
                v = random.randint(1, 10)
            else:
                power = random.randint(1, 8)
                v = random.randint(1, 10 ** power)
            ml = Milestones().previous(v)

            ts = now_ts() - random.randint(1, 30 * DAY)
            ts_prev = ts - random.randint(1, 30 * DAY)
            spec = random.choice(['BTC.BTC', 'ETH.ETH', 'DOGE.DOGE', 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48']) \
                if META_KEY_SPEC in ACHIEVEMENT_DESC_MAP[ach_key].description else ''
            rec = Achievement(ach_key, v, ml, ts, 200_000,
                              ts_prev, spec)

            print('TS: ', ts, datetime.datetime.fromtimestamp(rec.timestamp).strftime('%B %d, %Y'))

            await render_achievement_card(app, rec, loc, show=show)

            text = loc.notification_achievement_unlocked(rec)
            sep()
            print(text)
            sep()

        sep()
        print()
        sep()


async def demo_run_pipeline(app: LpAppFramework, ach_fet, spec_key_clear=None):
    ach_not = AchievementsNotifier(app.deps)
    ach_fet.add_subscriber(ach_not)
    ach_not.add_subscriber(app.deps.alert_presenter)

    # reset and clear
    await ach_not.cd.clear()
    await ach_not.tracker.delete_achievement_record(A.TEST)
    await ach_not.tracker.delete_achievement_record(A.TEST_SPEC, specialization=ach_fet.specialization)
    await ach_not.tracker.delete_achievement_record(A.TEST_DESCENDING)
    if spec_key_clear:
        await ach_not.tracker.delete_achievement_record(spec_key_clear)

    await ach_fet.run()


async def demo_run_pipeline_test(app: LpAppFramework, descending=False, spec=''):
    ach_fet = DebugAchievementsFetcher(app.deps.db, specialization=spec, descending=descending)
    await demo_run_pipeline(app, ach_fet)


async def demo_run_pipeline_coin_rank(app: LpAppFramework):
    ach_fet = DebugAchievementRank(app.deps, start=45, sleep_period=5)
    await demo_run_pipeline(app, ach_fet, spec_key_clear=A.COIN_MARKET_CAP_RANK)


def clear_temp_achievements_folder():
    source_folder = '../temp/a'
    os.makedirs(source_folder, exist_ok=True)
    for f in os.listdir(source_folder):
        if f.endswith('.png') and f.startswith('thorchain-ach'):
            path_to_delete = os.path.join(source_folder, f)
            os.remove(path_to_delete)
            print(f'Deleted: {path_to_delete}')


def gen_ach_desc_translate_mapping(items):
    sep()
    message = 'TRANSLATION_MAP = {\n'

    field_dict = {attr_v: attr for attr in dir(A) if isinstance((attr_v := getattr(A, attr)), str)}

    for item in items:
        item: AchievementDescription
        key = item.key
        key_name = field_dict.get(key)
        message += f'    A.{key_name}: "{item.description}",\n'

    message += '}\n'
    print(message)
    sep()


async def main():
    app = LpAppFramework()
    async with app:
        clear_temp_achievements_folder()
        # await demo_debug_logic(app)
        # await demo_achievements_picture(app, Language.ENGLISH, A.ANNIVERSARY, 3, 3)
        # await demo_achievements_picture(app, Language.RUSSIAN, A.ANNIVERSARY, 2, 2)
        await demo_achievements_picture(app, Language.ENGLISH, A.COIN_MARKET_CAP_RANK, 10, 11, descending=True)
        # await demo_achievements_picture(app, Language.RUSSIAN, A.COIN_MARKET_CAP_RANK, 10, 11, descending=True)
        # await demo_all_achievements(app)
        # await demo_run_pipeline_coin_rank(app)
        # await demo_run_pipeline_test(app, spec='BTC.BTC')
        # gen_ach_desc_translate_mapping(AchievementsEnglishLocalization())
        # gen_ach_desc_translate_mapping(AchievementsRussianLocalization())


if __name__ == '__main__':
    asyncio.run(main())
