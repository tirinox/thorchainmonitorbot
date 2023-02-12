from localization.achievements.common import A, ADesc, POSTFIX_RUNE, AchievementsLocalizationBase
from services.jobs.achievement.ach_list import Achievement
from services.lib.texts import code, pre


class AchievementsEnglishLocalization(AchievementsLocalizationBase):
    ACHIEVEMENT_DESC_LIST = [
        ADesc(A.TEST, 'Test metric'),
        ADesc(A.TEST_SPEC, 'Test metric', postfix=POSTFIX_RUNE),
        ADesc(A.TEST_DESCENDING, 'Test descending'),

        ADesc(A.DAU, 'Daily active users'),
        ADesc(A.MAU, 'Monthly active users'),
        ADesc(A.WALLET_COUNT, 'Number of wallets'),
        ADesc(A.SWAP_COUNT_TOTAL, 'Total swap count'),
        ADesc(A.SWAP_COUNT_24H, '24h swap count'),
        ADesc(A.SWAP_COUNT_30D, 'Monthly swap count'),
        ADesc(A.SWAP_UNIQUE_COUNT, 'Unique swappers'),
        ADesc(A.ADD_LIQUIDITY_COUNT_TOTAL, 'Total add liquidity count'),
        ADesc(A.ADD_LIQUIDITY_VOLUME_TOTAL, 'Total add liquidity volume'),
        ADesc(A.DAILY_VOLUME, 'Daily volume', prefix='$'),
        ADesc(A.ILP_PAID_TOTAL, 'Total ILP paid', postfix=POSTFIX_RUNE),
        ADesc(A.TOTAL_ACTIVE_BOND, 'Total active bond'),
        ADesc(A.TOTAL_BOND, 'Total bond', postfix=POSTFIX_RUNE),
        ADesc(A.NODE_COUNT, 'Total nodes count', postfix=POSTFIX_RUNE),
        ADesc(A.ACTIVE_NODE_COUNT, 'Active nodes count'),

        ADesc(A.ANNIVERSARY, 'Anniversary'),
        ADesc(A.BLOCK_NUMBER, 'Blocks generated'),
        ADesc(A.DAILY_TX_COUNT, 'Daily TX count'),
        ADesc(A.TOTAL_MIMIR_VOTES, 'Total Mimir votes'),
        ADesc(A.MARKET_CAP_USD, 'Rune Total Market Cap', prefix='$'),
        ADesc(A.TOTAL_POOLS, 'Total pools'),
        ADesc(A.TOTAL_ACTIVE_POOLS, 'Active pools'),

        ADesc(A.TOTAL_UNIQUE_SAVERS, 'Total unique savers'),
        ADesc(A.TOTAL_SAVED_USD, 'Total USD saved', prefix='$'),
        ADesc(A.TOTAL_SAVERS_EARNED_USD, 'Savers: Total USD earned', prefix='$'),

        ADesc(A.SAVER_VAULT_SAVED_ASSET, '::asset:: Savers depth'),
        ADesc(A.SAVER_VAULT_SAVED_USD, '::asset:: Savers depth in USD', prefix='$'),
        ADesc(A.SAVER_VAULT_MEMBERS, '::asset:: savers count'),
        ADesc(A.SAVER_VAULT_EARNED_ASSET, 'Savers earned ::asset::'),

        ADesc(A.SWAP_VOLUME_TOTAL_RUNE, 'Total swap volume', postfix=POSTFIX_RUNE),

        ADesc(A.MAX_SWAP_AMOUNT_USD, 'Maximum swap volume', prefix='$'),
        ADesc(A.MAX_ADD_AMOUNT_USD, 'Maximum add liquidity volume', prefix='$'),

        ADesc(A.MAX_ADD_AMOUNT_USD_PER_POOL, 'Added ::asset:: in a single TX', prefix='$'),

        ADesc(A.COIN_MARKET_CAP_RANK, 'Market cap rank'),
    ]

    CELEBRATION_EMOJIES = "🎉🎊🥳🙌🥂🪅🎆"

    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)
        desc: ADesc

        msg = f'{emoji} <b>THORChain has reached a new milestone!</b>\n'

        if a.key == a.ANNIVERSARY:
            # special case for anniversary
            msg += f"Happy Birthday! It's been {milestone_str} years since the first block!"
        else:
            # default case
            if value_str:
                value_str = f' ({pre(value_str)})'
            msg += f'{pre(desc_str)} is now over {code(milestone_str)}{value_str}!'
            if a.has_previous:
                msg += f'\nPrevious milestone was {pre(prev_milestone_str)} ({ago} ago)'

        if desc.url:
            msg += f'\n{desc.url}'

        return msg
