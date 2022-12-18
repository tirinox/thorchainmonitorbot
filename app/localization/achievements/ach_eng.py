from typing import NamedTuple

from services.jobs.achievements import EventAchievement, Achievement
from services.lib.date_utils import seconds_human
from services.lib.texts import code, pre


class AchievementDescription(NamedTuple):
    key: str
    description: str
    postfix: str = ''
    prefix: str = ''
    url: str = ''  # url to the dashboard

    @property
    def image(self):
        return f'ach_{self.key}.png'


ACHIEVEMENT_DESC_LIST = [
    AchievementDescription(Achievement.TEST, 'Test achievement'),
    AchievementDescription(Achievement.DAU, 'Daily active users'),
    AchievementDescription(Achievement.MAU, 'Monthly active users'),
    AchievementDescription(Achievement.WALLET_COUNT, 'Wallets count'),
    AchievementDescription(Achievement.SWAP_COUNT_TOTAL, 'Total swaps count'),
    AchievementDescription(Achievement.SWAP_COUNT_24H, '24h swaps count'),
    AchievementDescription(Achievement.SWAP_COUNT_30D, 'Monthly swap count'),
    AchievementDescription(Achievement.SWAP_UNIQUE_COUNT, 'Unique swappers'),
    AchievementDescription(Achievement.ADD_LIQUIDITY_COUNT_TOTAL, 'Total add liquidity count'),
    AchievementDescription(Achievement.ADD_LIQUIDITY_VOLUME_TOTAL, 'Total add liquidity volume'),
    AchievementDescription(Achievement.DAILY_VOLUME, 'Daily volume'),
    AchievementDescription(Achievement.ILP_PAID_TOTAL, 'Total ILP paid'),
    AchievementDescription(Achievement.TOTAL_ACTIVE_BOND, 'Total active bond'),
    AchievementDescription(Achievement.TOTAL_BOND, 'Total bond'),
    AchievementDescription(Achievement.NODE_COUNT, 'Total nodes count'),
    AchievementDescription(Achievement.ACTIVE_NODE_COUNT, 'Active nodes count'),
    AchievementDescription(Achievement.CHURNED_IN_BOND, 'Churned in bond'),
    AchievementDescription(Achievement.ANNIVERSARY, 'Anniversary'),
    AchievementDescription(Achievement.BLOCK_NUMBER, 'Blocks generated'),
    AchievementDescription(Achievement.DAILY_TX_COUNT, 'Daily TX count'),
]

ACHIEVEMENT_DESC_MAP = {a.key: a for a in ACHIEVEMENT_DESC_LIST}


def check_if_all_achievements_have_description():
    all_achievements = set(Achievement.all_keys())
    all_achievements_with_desc = set(ACHIEVEMENT_DESC_MAP.keys())
    assert all_achievements == all_achievements_with_desc, \
        f'Not all achievements have description. Missing: {all_achievements - all_achievements_with_desc}'


check_if_all_achievements_have_description()


class AchievementsEnglishLocalization:
    @staticmethod
    def notification_achievement_unlocked(e: EventAchievement):
        a = e.achievement
        ago = seconds_human(a.timestamp - a.previous_ts)
        return f'<b>You have unlocked achievement "{a.key}"!</b> ' \
               f'{code(a.key)} is over {a.milestone} ({pre(a.value)})\n (was {a.prev_milestone} {ago})'
