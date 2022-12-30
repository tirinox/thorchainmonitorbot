import random
from typing import NamedTuple

from services.jobs.achievements import EventAchievement, Achievement
from services.lib.date_utils import seconds_human
from services.lib.money import short_money
from services.lib.texts import code, pre

POST_FIX_RUNE = ' R'


class AchievementDescription(NamedTuple):
    key: str
    description: str
    postfix: str = ''
    prefix: str = ''
    url: str = ''  # url to the dashboard
    signed: bool = False

    @property
    def image(self):
        return f'ach_{self.key}.png'

    def format_value(self, value):
        return short_money(value, prefix=self.prefix, postfix=self.postfix, integer=True, signed=self.signed)


ACHIEVEMENT_DESC_LIST = [
    AchievementDescription(Achievement.TEST, 'Test metric'),
    AchievementDescription(Achievement.DAU, 'Daily active users'),
    AchievementDescription(Achievement.MAU, 'Monthly active users'),
    AchievementDescription(Achievement.WALLET_COUNT, 'Wallets count'),
    AchievementDescription(Achievement.SWAP_COUNT_TOTAL, 'Total swaps count'),
    AchievementDescription(Achievement.SWAP_COUNT_24H, '24h swaps count'),
    AchievementDescription(Achievement.SWAP_COUNT_30D, 'Monthly swap count'),
    AchievementDescription(Achievement.SWAP_UNIQUE_COUNT, 'Unique swappers'),
    AchievementDescription(Achievement.ADD_LIQUIDITY_COUNT_TOTAL, 'Total add liquidity count'),
    AchievementDescription(Achievement.ADD_LIQUIDITY_VOLUME_TOTAL, 'Total add liquidity volume'),
    AchievementDescription(Achievement.DAILY_VOLUME, 'Daily volume', prefix='$'),
    AchievementDescription(Achievement.ILP_PAID_TOTAL, 'Total ILP paid', postfix=POST_FIX_RUNE),
    AchievementDescription(Achievement.TOTAL_ACTIVE_BOND, 'Total active bond'),
    AchievementDescription(Achievement.TOTAL_BOND, 'Total bond', postfix=POST_FIX_RUNE),
    AchievementDescription(Achievement.NODE_COUNT, 'Total nodes count', postfix=POST_FIX_RUNE),
    AchievementDescription(Achievement.ACTIVE_NODE_COUNT, 'Active nodes count'),
    AchievementDescription(Achievement.CHURNED_IN_BOND, 'Churned in bond', postfix=POST_FIX_RUNE),
    AchievementDescription(Achievement.ANNIVERSARY, 'Anniversary'),
    AchievementDescription(Achievement.BLOCK_NUMBER, 'Blocks generated'),
    AchievementDescription(Achievement.DAILY_TX_COUNT, 'Daily TX count'),
    AchievementDescription(Achievement.TOTAL_MIMIR_VOTES, 'Total Mimir votes'),
    AchievementDescription(Achievement.MARKET_CAP_USD, 'Rune Total Market Cap', prefix='$'),
    AchievementDescription(Achievement.TOTAL_POOLS, 'Total pools'),
    AchievementDescription(Achievement.TOTAL_ACTIVE_POOLS, 'Active pools'),
]

ACHIEVEMENT_DESC_MAP = {a.key: a for a in ACHIEVEMENT_DESC_LIST}


def check_if_all_achievements_have_description():
    all_achievements = set(Achievement.all_keys())
    all_achievements_with_desc = set(ACHIEVEMENT_DESC_MAP.keys())
    assert all_achievements == all_achievements_with_desc, \
        f'Not all achievements have description. Missing: {all_achievements - all_achievements_with_desc}'


check_if_all_achievements_have_description()


class AchievementsEnglishLocalization:
    CELEBRATION_EMOJIES = "🎉🎊🥳🙌🥂🪅🎆"

    @staticmethod
    def get_achievement_description(achievement: str) -> AchievementDescription:
        return ACHIEVEMENT_DESC_MAP[achievement]

    @classmethod
    def notification_achievement_unlocked(cls, e: EventAchievement):
        ago, desc, emoji, milestone_str, prev_milestone_str, value_str = cls._prepare_achievement_data(e)

        return (
            f'{emoji} <b>A new achievement has been unlocked</b>\n'
            f'{pre(desc.description)} is now over {code(milestone_str)} ({pre(value_str)})!\n '
            f'Previously value: {pre(prev_milestone_str)} ({ago} ago)'
        )

    @classmethod
    def _prepare_achievement_data(cls, e: EventAchievement):
        a = e.achievement
        desc = cls.get_achievement_description(a.key)
        emoji = random.choice(cls.CELEBRATION_EMOJIES)
        ago = seconds_human(a.timestamp - a.previous_ts)
        milestone_str = desc.format_value(a.milestone)
        value_str = desc.format_value(a.value)
        prev_milestone_str = desc.format_value(a.prev_milestone)
        return ago, desc, emoji, milestone_str, prev_milestone_str, value_str
