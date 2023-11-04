from localization.achievements.common import AchievementsLocalizationBase
from services.jobs.achievement.ach_list import Achievement, A, ADesc
from services.lib.texts import code, pre


class AchievementsEnglishLocalization(AchievementsLocalizationBase):
    TRANSLATION_MAP = {
        A.TEST: "Test metric",
        A.TEST_SPEC: "Test metric",
        A.TEST_DESCENDING: "Test descending",
        A.DAU: "Daily active users",
        A.MAU: "Monthly active users",
        A.WALLET_COUNT: "Number of wallets",
        A.SWAP_COUNT_TOTAL: "Total swap count",
        A.SWAP_COUNT_24H: "24h swap count",
        A.SWAP_COUNT_30D: "Monthly swap count",
        A.ADD_LIQUIDITY_COUNT_TOTAL: "Times liquidity added",
        A.ADD_LIQUIDITY_VOLUME_TOTAL: "Total add liquidity volume",
        A.DAILY_VOLUME: "Daily volume",
        A.ILP_PAID_TOTAL: "Total ILP paid",
        A.TOTAL_ACTIVE_BOND: "Total active bond",
        A.TOTAL_BOND: "Total bond",
        A.NODE_COUNT: "Total nodes count",
        A.ACTIVE_NODE_COUNT: "Active nodes count",
        A.ANNIVERSARY: "Anniversary",
        A.BLOCK_NUMBER: "Blocks generated",
        A.DAILY_TX_COUNT: "Daily TX count",
        A.TOTAL_MIMIR_VOTES: "Total Mimir votes",
        A.MARKET_CAP_USD: "Rune Total Market Cap",
        A.TOTAL_POOLS: "Total pools",
        A.TOTAL_ACTIVE_POOLS: "Active pools",
        A.TOTAL_UNIQUE_SAVERS: "Total unique savers",
        A.TOTAL_SAVED_USD: "Total USD saved",
        A.TOTAL_SAVERS_EARNED_USD: "Savers: Total USD earned",
        A.SAVER_VAULT_SAVED_ASSET: "::asset:: Savers depth",
        A.SAVER_VAULT_SAVED_USD: "::asset:: Savers depth in USD",
        A.SAVER_VAULT_MEMBERS: "::asset:: savers count",
        A.SAVER_VAULT_EARNED_ASSET: "Savers earned ::asset::",
        A.SWAP_VOLUME_TOTAL_RUNE: "Total swap volume",
        A.MAX_SWAP_AMOUNT_USD: "Maximum swap volume",
        A.MAX_ADD_AMOUNT_USD: "Maximum add liquidity volume",
        A.MAX_ADD_AMOUNT_USD_PER_POOL: "Added ::asset:: in a single TX",
        A.COIN_MARKET_CAP_RANK: "Market cap rank",
        A.POL_VALUE_RUNE: "POL maximum value",
        A.BTC_IN_VAULT: "Bitcoin in vaults",
        A.ETH_IN_VAULT: "Ethereum in vaults",
        A.STABLES_IN_VAULT: "Stable coins in vaults",

        A.TOTAL_VALUE_LOCKED: "Total value locked",
        A.WEEKLY_SWAP_VOLUME: "Weekly swap volume",
        A.WEEKLY_PROTOCOL_REVENUE_USD: "Weekly protocol revenue",
        A.WEEKLY_AFFILIATE_REVENUE_USD: "Weekly affiliate revenue",

        A.RUNE_BURNT_LENDING: "RUNE burnt",
    }

    CELEBRATION_EMOJIES = "🎉🎊🥳🙌🥂🪅🎆"

    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)
        desc: ADesc

        msg = f'{emoji} <b>THORChain has hit a new milestone!</b>\n'

        if a.key == A.ANNIVERSARY:
            # special case for anniversary
            msg += f"Happy Birthday! It's been {milestone_str} years since the first block!"
        elif a.key == A.COIN_MARKET_CAP_RANK:
            msg += f"THORChain Rune is <b>#{milestone_str}</b> largest coin my market cap!"
            if a.has_previous:
                msg += f'\nPreviously #{prev_milestone_str} ({ago} ago)'
        else:
            # default case
            if value_str:
                value_str = f' ({pre(value_str)})'

            relation_str = 'is now less than' if a.descending else 'is now over'

            msg += f'{pre(desc_str)} {relation_str} {code(milestone_str)}{value_str}!'
            if a.has_previous:
                msg += f'\nPrevious milestone was {pre(prev_milestone_str)} ({ago} ago)'

        if desc.url:
            msg += f'\n{desc.url}'

        return msg
