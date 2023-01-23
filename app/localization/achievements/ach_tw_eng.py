from localization.achievements.ach_eng import AchievementsEnglishLocalization

from services.jobs.achievements import Achievement


class AchievementsTwitterEnglishLocalization(AchievementsEnglishLocalization):
    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)

        msg = f'{emoji} <b>@THORChain has reached a new milestone!</b>\n'

        if a.key == a.ANNIVERSARY:
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
