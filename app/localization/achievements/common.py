import abc
import random

from services.jobs.achievement.ach_list import AchievementDescription, Achievement, META_KEY_SPEC, AchievementName, \
    ACHIEVEMENT_DESC_MAP
from services.lib.date_utils import seconds_human


class AchievementsLocalizationBase(abc.ABC):
    CELEBRATION_EMOJIES = "🎉🎊🥳🙌🥂🪅🎆"
    DEVIATION_TO_SHOW_VALUE_PCT = 10
    MORE_THAN = 'More than'
    TRANSLATION_MAP = {}  # fill in

    @classmethod
    def check_if_all_achievements_have_description(cls):
        all_achievements = set(AchievementName.all_keys())
        all_achievements_with_desc = set(a for a in ACHIEVEMENT_DESC_MAP)
        assert all_achievements == all_achievements_with_desc, \
            f'Not all achievements have description. Missing: {all_achievements - all_achievements_with_desc}'

    def get_achievement_description(self, achievement_key: str) -> AchievementDescription:
        # return self.desc_map.get(achievement, 'Unknown achievement. Please contact support')
        desc = ACHIEVEMENT_DESC_MAP.get(achievement_key)
        if not desc:
            raise ValueError(f'Unknown achievement {achievement_key!r}')

        desc: AchievementDescription

        new_desc = self.TRANSLATION_MAP.get(achievement_key)

        return desc._replace(description=new_desc)

    @classmethod
    def _do_substitutions(cls, achievement: Achievement, text: str) -> str:
        return text.replace(META_KEY_SPEC, achievement.specialization)

    def prepare_achievement_data(self, a: Achievement, newlines=False):
        desc = self.get_achievement_description(a.key)
        emoji = random.choice(self.CELEBRATION_EMOJIES)
        ago = seconds_human(a.timestamp - a.previous_ts) if a.previous_ts and a.has_previous else ''

        # Milestone string is used as the main number on the picture
        if a.descending:
            # show the real value for descending sequences
            milestone_str = desc.format_value(a.value, a)
        else:
            milestone_str = desc.format_value(a.milestone, a)

        prev_milestone_str = desc.format_value(a.prev_milestone, a)

        # Description
        desc_text = desc.description
        desc_text = self._do_substitutions(a, desc_text)
        if not newlines:
            desc_text = desc_text.replace('\n', ' ')

        # Value string (goes in parentheses after the milestone_str)
        value_str = ''
        if a.value and not a.descending:
            if abs(a.value - a.milestone) < 0.01 * self.DEVIATION_TO_SHOW_VALUE_PCT * a.milestone:
                value_str = ''
            else:
                value_str = desc.format_value(a.value, a)
            value_str = self._do_substitutions(a, value_str)

        return desc, ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str

    def __init__(self):
        self.check_if_all_achievements_have_description()

    @abc.abstractmethod
    def notification_achievement_unlocked(self, a: Achievement):
        ...
