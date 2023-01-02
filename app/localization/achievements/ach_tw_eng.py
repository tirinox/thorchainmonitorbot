from localization.achievements.ach_eng import AchievementsEnglishLocalization

from services.jobs.achievements import Achievement


class AchievementsTwitterEnglishLocalization(AchievementsEnglishLocalization):
    @classmethod
    def notification_achievement_unlocked(cls, e: Achievement):
        ago, desc, emoji, milestone_str, prev_milestone_str, value_str = cls._prepare_achievement_data(e)

        return (
            f'{emoji} @THORChain has accomplished a new achievement!\n'
            f'"{desc}" is now over {milestone_str} ({value_str})!\n'
            f'Previous milestone was {prev_milestone_str} ({ago} ago)'
        )
