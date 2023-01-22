from localization.achievements.common import A, ADesc, POSTFIX_RUNE, META_KEY_SPEC, \
    AchievementsLocalizationBase
from services.jobs.achievements import Achievement
from services.lib.texts import code, pre


class AchievementsEnglishLocalization(AchievementsLocalizationBase):
    ACHIEVEMENT_DESC_LIST = [
        ADesc(A.TEST, 'Test metric'),
        ADesc(A.TEST_SPEC, 'Test metric', postfix=META_KEY_SPEC),

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
        ADesc(A.TOTAL_SAVERS_EARNED_USD, 'Total USD earned', prefix='$'),

        ADesc(A.SAVER_VAULT_SAVED_ASSET, 'Savers depth ::asset::'),
        ADesc(A.SAVER_VAULT_SAVED_USD, 'Savers depth ::asset::: in USD', prefix='$'),
        ADesc(A.SAVER_VAULT_MEMBERS, '::asset:: savers count'),
        ADesc(A.SAVER_VAULT_EARNED_ASSET, 'Savers earned ::asset::'),
    ]

    CELEBRATION_EMOJIES = "🎉🎊🥳🙌🥂🪅🎆"

    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)
        desc: ADesc

        msg = f'{emoji} <b>THORChain has accomplished a new achievement!</b>\n'

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
