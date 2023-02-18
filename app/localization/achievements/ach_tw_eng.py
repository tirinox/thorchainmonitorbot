from localization.achievements.ach_eng import AchievementsEnglishLocalization

from services.jobs.achievement.ach_list import Achievement, A


class AchievementsTwitterEnglishLocalization(AchievementsEnglishLocalization):
    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)

        msg = f'{emoji} @THORChain has reached a new milestone!\n'

        if a.key == A.ANNIVERSARY:
            # special case for anniversary
            msg += f"Happy Birthday! It's been {milestone_str} years since the first block!"
        else:
            # default case
            if value_str:
                value_str = f' ({value_str})'
            msg += f'{desc_str} is now over {milestone_str}{value_str}!'
            if a.has_previous:
                msg += f'\nPrevious milestone was {prev_milestone_str} ({ago} ago)'

        if desc.url:
            msg += f'\n{desc.url}'

        return msg
