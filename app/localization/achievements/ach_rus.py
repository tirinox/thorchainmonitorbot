from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.jobs.achievements import Achievement
from services.lib.texts import code, pre


# todo: localize Achievement contents

class AchievementsRussianLocalization(AchievementsEnglishLocalization):
    @classmethod
    def notification_achievement_unlocked(cls, a: Achievement):
        ago, desc, emoji, milestone_str, prev_milestone_str, value_str = cls._prepare_achievement_data(a)

        return (
            f'{emoji} <b>THORChain совершил новое достижение!</b>\n'
            f'{pre(desc)} теперь больше, чем {code(milestone_str)} ({pre(value_str)})!\n'
            f'Предыдущая веха: {pre(prev_milestone_str)} ({ago} назад)'
        )
