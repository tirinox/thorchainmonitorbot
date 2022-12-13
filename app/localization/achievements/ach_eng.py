from typing import NamedTuple

from services.jobs.achievements import EventAchievement, Achievement
from services.lib.date_utils import seconds_human
from services.lib.texts import code, pre


class AchievementDescription(NamedTuple):
    key: str
    description: str
    postfix: str = ''
    prefix: str = ''

    @property
    def image(self):
        return f'ach_{self.key}.png'


LIST = [
    AchievementDescription(Achievement.DAU, 'Daily active users'),
    AchievementDescription(Achievement.MAU, 'Monthly active users'),
    AchievementDescription(Achievement.WALLET_COUNT, 'Wallets count'),
    AchievementDescription(Achievement.TEST, 'Test achievement'),
]


class AchievementsEnglishLocalization:
    @staticmethod
    def notification_achievement_unlocked(e: EventAchievement):
        a = e.achievement
        ago = seconds_human(a.timestamp - a.previous_ts)
        return f'<b>You have unlocked achievement "{a.key}"!</b> ' \
               f'{code(a.key)} is over {a.milestone} ({pre(a.value)})\n (was {a.prev_milestone} {ago})'
