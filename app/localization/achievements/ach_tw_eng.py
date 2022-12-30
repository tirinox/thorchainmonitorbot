from localization.achievements.ach_eng import AchievementsEnglishLocalization

from services.jobs.achievements import EventAchievement


class AchievementsTwitterEnglishLocalization(AchievementsEnglishLocalization):
    @classmethod
    def notification_achievement_unlocked(cls, e: EventAchievement):
        ago, desc, emoji, milestone_str, prev_milestone_str, value_str = cls._prepare_achievement_data(e)

        return (
            f'{emoji} A new achievement has been unlocked\n'
            f'{desc.description} is now over {milestone_str} ({value_str})!\n '
            f'Previously value: {prev_milestone_str} ({ago} ago)'
        )
