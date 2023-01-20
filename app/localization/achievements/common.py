import random
from typing import NamedTuple

from services.jobs.achievements import Achievement
from services.lib.date_utils import seconds_human
from services.lib.money import short_money, RAIDO_GLYPH


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
POSTFIX_RUNE = RAIDO_GLYPH
META_KEY_SPEC = '::asset::'


class AchievementsLocalizationBase:
    ACHIEVEMENT_DESC_LIST = []
    CELEBRATION_EMOJIES = "🎉🎊🥳🙌🥂🪅🎆"

    @classmethod
    def check_if_all_achievements_have_description(cls):
        all_achievements = set(A.all_keys())
        all_achievements_with_desc = set(a.key for a in cls.ACHIEVEMENT_DESC_LIST)
        assert all_achievements == all_achievements_with_desc, \
            f'Not all achievements have description. Missing: {all_achievements - all_achievements_with_desc}'

    def get_achievement_description(self, achievement: str) -> AchievementDescription:
        return self.desc_map.get(achievement, 'Unknown achievement. Please contact support')

    @classmethod
    def _do_substitutions(cls, achievement: Achievement, text: str) -> str:
        return text.replace(META_KEY_SPEC, achievement.specialization)

    def prepare_achievement_data(self, a: Achievement, newlines=False):
        desc = self.get_achievement_description(a.key)
        emoji = random.choice(self.CELEBRATION_EMOJIES)
        ago = seconds_human(a.timestamp - a.previous_ts) if a.previous_ts else ''
        milestone_str = desc.format_value(a.milestone, a)
        prev_milestone_str = desc.format_value(a.prev_milestone, a)

        desc_text = desc.description
        desc_text = self._do_substitutions(a, desc_text)
        if not newlines:
            desc_text = desc_text.replace('\n', ' ')

        if a.value and abs(a.value - a.milestone) < 0.01 * a.milestone:
            value_str = ''
        else:
            value_str = desc.format_value(a.value, a)
        value_str = self._do_substitutions(a, value_str)

        return ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str

    def __init__(self):
        self.desc_map = {a.key: a for a in self.ACHIEVEMENT_DESC_LIST}
        self.check_if_all_achievements_have_description()
