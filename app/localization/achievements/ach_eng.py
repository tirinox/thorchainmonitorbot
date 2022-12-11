from services.jobs.achievements import EventAchievement
from services.lib.date_utils import seconds_human, now_ts
from services.lib.texts import code, pre


class AchievementsEnglishLocalization:
    @staticmethod
    def notification_achievement_unlocked(e: EventAchievement):
        a = e.achievement
        ago = seconds_human(now_ts() - a.last_ts)
        return f'<b>You have unlocked achievement "{a.key}"!</b> ' \
               f'{code(a.key)} is over {a.milestone} ({pre(a.value)})\n (was {a.prev_milestone} {ago})'
