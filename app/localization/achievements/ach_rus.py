from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.jobs.achievements import EventAchievement
from services.lib.texts import code, pre


# todo: localize Achievement contents

class AchievementsRussianLocalization(AchievementsEnglishLocalization):
    @classmethod
    def notification_achievement_unlocked(cls, e: EventAchievement):
        ago, desc, emoji, milestone_str, prev_milestone_str, value_str = cls._prepare_achievement_data(e)

        return (
            f'{emoji} <b>Открыто новое достижение</b>\n'
            f'{pre(desc.description)} теперь больше, чем {code(milestone_str)} ({pre(value_str)})!\n '
            f'Предыдущее значение: {pre(prev_milestone_str)} ({ago} назад)'
        )
