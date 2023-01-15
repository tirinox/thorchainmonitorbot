import random
from typing import NamedTuple

from services.jobs.achievements import Achievement
from services.lib.date_utils import seconds_human
from services.lib.money import short_money
from services.lib.texts import code, pre


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

    @staticmethod
    def space_before_non_empty(s):
        return f' {s}' if s else ''

    @classmethod
    def _do_substitutions(cls, achievement: Achievement, text: str) -> str:
        return text.replace(META_KEY_SPEC, achievement.specialization)

    def format_value(self, value, ach: Achievement):
        return short_money(value,
                           prefix=self._do_substitutions(ach, self.prefix),
                           postfix=self.space_before_non_empty(self._do_substitutions(ach, self.postfix)),
                           integer=True, signed=self.signed)


A = Achievement
ADesc = AchievementDescription
POSTFIX_RUNE = ' R'

META_KEY_SPEC = '::asset::'

ACHIEVEMENT_DESC_LIST = [
    ADesc(A.TEST, 'Test metric'),
    ADesc(A.TEST_SPEC, 'Test metric', postfix=META_KEY_SPEC),
    ADesc(A.DAU, 'Daily active users'),
    ADesc(A.MAU, 'Monthly active users'),
    ADesc(A.WALLET_COUNT, 'Wallets count'),
    ADesc(A.SWAP_COUNT_TOTAL, 'Total swaps count'),
    ADesc(A.SWAP_COUNT_24H, '24h swaps count'),
    ADesc(A.SWAP_COUNT_30D, 'Monthly swap count'),
    ADesc(A.SWAP_UNIQUE_COUNT, 'Unique swappers'),
    ADesc(A.ADD_LIQUIDITY_COUNT_TOTAL, 'Total add liquidity count'),
    ADesc(A.ADD_LIQUIDITY_VOLUME_TOTAL, 'Total add liquidity volume'),
    ADesc(A.DAILY_VOLUME, 'Daily volume', prefix='$'),
    ADesc(A.ILP_PAID_TOTAL, 'Total ILP paid', postfix=POSTFIX_RUNE),
    ADesc(A.TOTAL_ACTIVE_BOND, 'Total active bond'),
    ADesc(A.TOTAL_BOND, 'Total bond', postfix=POSTFIX_RUNE),
    ADesc(A.NODE_COUNT, 'Total nodes count', postfix=POSTFIX_RUNE),
    ADesc(A.ACTIVE_NODE_COUNT, 'Active nodes count'),
    ADesc(A.CHURNED_IN_BOND, 'Churned in bond', postfix=POSTFIX_RUNE),
    ADesc(A.ANNIVERSARY, 'Anniversary'),  # todo: special emoji
    ADesc(A.BLOCK_NUMBER, 'Blocks generated'),
    ADesc(A.DAILY_TX_COUNT, 'Daily TX count'),
    ADesc(A.TOTAL_MIMIR_VOTES, 'Total Mimir votes'),
    ADesc(A.MARKET_CAP_USD, 'Rune Total Market Cap', prefix='$'),
    ADesc(A.TOTAL_POOLS, 'Total pools'),
    ADesc(A.TOTAL_ACTIVE_POOLS, 'Active pools'),

    ADesc(A.TOTAL_UNIQUE_SAVERS, 'Total unique savers'),
    ADesc(A.TOTAL_SAVED_USD, 'Total USD saved', prefix='$'),
    ADesc(A.TOTAL_SAVERS_EARNED_USD, 'Total USD earned', prefix='$'),

    ADesc(A.SAVER_VAULT_SAVED_ASSET, 'Total saved ::asset::'),
    ADesc(A.SAVER_VAULT_SAVED_USD, 'Savers vault ::asset::: total saved USD', prefix='$'),
    ADesc(A.SAVER_VAULT_MEMBERS, '::asset:: Savers vault members'),
    ADesc(A.SAVER_VAULT_EARNED_ASSET, 'Savers earned ::asset::'),
]

ACHIEVEMENT_DESC_MAP = {a.key: a for a in ACHIEVEMENT_DESC_LIST}


def check_if_all_achievements_have_description():
    all_achievements = set(A.all_keys())
    all_achievements_with_desc = set(ACHIEVEMENT_DESC_MAP.keys())
    assert all_achievements == all_achievements_with_desc, \
        f'Not all achievements have description. Missing: {all_achievements - all_achievements_with_desc}'


check_if_all_achievements_have_description()


class AchievementsEnglishLocalization:
    CELEBRATION_EMOJIES = "🎉🎊🥳🙌🥂🪅🎆"

    @staticmethod
    def get_achievement_description(achievement: str) -> AchievementDescription:
        return ACHIEVEMENT_DESC_MAP.get(achievement, 'Unknown achievement. Please contact support')

    @classmethod
    def notification_achievement_unlocked(cls, a: Achievement):
        ago, desc, emoji, milestone_str, prev_milestone_str, value_str = cls.prepare_achievement_data(a)

        msg = (
            f'{emoji} <b>THORChain has accomplished a new achievement!</b>\n'
            f'{pre(desc)} is now over {code(milestone_str)} ({pre(value_str)})!'
        )

        if a.has_previous:
            msg += f'\nPrevious milestone was {pre(prev_milestone_str)} ({ago} ago)'

        return msg

    @classmethod
    def _do_substitutions(cls, achievement: Achievement, text: str) -> str:
        return text.replace(META_KEY_SPEC, achievement.specialization)

    @classmethod
    def prepare_achievement_data(cls, a: Achievement):
        desc = cls.get_achievement_description(a.key)
        emoji = random.choice(cls.CELEBRATION_EMOJIES)
        ago = seconds_human(a.timestamp - a.previous_ts)
        milestone_str = desc.format_value(a.milestone, a)
        value_str = desc.format_value(a.value, a)
        prev_milestone_str = desc.format_value(a.prev_milestone, a)
        desc_text = desc.description
        desc_text = cls._do_substitutions(a, desc_text)
        value_str = cls._do_substitutions(a, value_str)
        return ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str
