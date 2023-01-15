from localization.achievements.ach_eng import AchievementsEnglishLocalization

from services.jobs.achievements import Achievement


class AchievementsTwitterEnglishLocalization(AchievementsEnglishLocalization):
    @classmethod
    def notification_achievement_unlocked(cls, a: Achievement):
        ago, desc, emoji, milestone_str, prev_milestone_str, value_str = cls.prepare_achievement_data(a)

        msg = (
            f'{emoji} @THORChain has accomplished a new achievement!\n'
            f'"{desc}" is now over {milestone_str} ({value_str})!'
        )

        if a.has_previous:
            msg += f'\nPrevious milestone was {prev_milestone_str} ({ago} ago)'

        return msg
