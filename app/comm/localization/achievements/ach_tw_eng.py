from comm.localization.achievements.ach_eng import AchievementsEnglishLocalization

from jobs.achievement.ach_list import Achievement, A


class AchievementsTwitterEnglishLocalization(AchievementsEnglishLocalization):
    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)

        msg = f'{emoji} @THORChain has hit a new milestone!\n'

        if a.key == A.ANNIVERSARY:
            # special case for anniversary
            msg += f"Happy Birthday! It's been {milestone_str} years since the first block!"
        elif a.key == A.COIN_MARKET_CAP_RANK:
            msg += f".@THORChain Rune is #{milestone_str} largest coin my market cap!"
            if a.has_previous:
                msg += f'\nPreviously #{prev_milestone_str} ({ago} ago)'
        else:
            # default case
            if value_str:
                value_str = f' ({value_str})'

            relation_str = 'is now less than' if a.descending else 'is now over'

            msg += f'{desc_str} {relation_str} {milestone_str}{value_str}!'

            if a.has_previous:
                msg += f'\nPrevious milestone was {prev_milestone_str} ({ago} ago)'

        if desc.url:
            msg += f'\n{desc.url}'

        return msg
