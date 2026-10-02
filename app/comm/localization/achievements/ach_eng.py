from jobs.achievement.ach_list import Achievement, A, ADesc
from lib.texts import code, pre
from .common import AchievementsLocalizationBase


class AchievementsEnglishLocalization(AchievementsLocalizationBase):
    TRANSLATION_MAP = {
        A.TEST: "Test metric",
        A.TEST_SPEC: "Test metric",
        A.TEST_DESCENDING: "Test descending",
        A.DAU: "Daily active users",
        A.MAU: "Monthly active users",
        A.WALLET_COUNT: "Wallets",
        A.SWAP_COUNT_TOTAL: "Total swaps",
        A.SWAP_COUNT_24H: "Swaps in 24h",
        A.SWAP_COUNT_30D: "Monthly swaps",
        A.ADD_LIQUIDITY_COUNT_TOTAL: "Liquidity additions",
        A.ADD_LIQUIDITY_VOLUME_TOTAL: "Total liquidity added",
        A.DAILY_VOLUME: "Daily swap volume",
        A.MONTHLY_SWAP_VOLUME: "Monthly swap volume",
        A.TOTAL_ACTIVE_BOND: "Total active bond",
        A.TOTAL_BOND: "Total bond",
        A.NODE_COUNT: "Total node count",
        A.ACTIVE_NODE_COUNT: "Active node count",
        A.ANNIVERSARY: "Anniversary",
        A.BLOCK_NUMBER: "Blocks produced",
        A.DAILY_TX_COUNT: "Daily transactions",
        A.TOTAL_MIMIR_VOTES: "Total Mimir votes",
        A.MARKET_CAP_USD: "RUNE market cap",
        A.TOTAL_POOLS: "Total pools",
        A.TOTAL_ACTIVE_POOLS: "Active pools",
        A.SWAP_VOLUME_TOTAL_USD: "Total swap volume",
        A.MAX_SWAP_AMOUNT_USD: "Largest single swap",
        A.MAX_ADD_AMOUNT_USD: "Largest single liquidity add",
        A.COIN_MARKET_CAP_RANK: "By market cap",
        A.POL_VALUE_USD: "POL value",
        A.BTC_IN_VAULT: "Bitcoin in vaults",
        A.ETH_IN_VAULT: "Ethereum in vaults",
        A.STABLES_IN_VAULT: "Stablecoins in vaults",

        A.TOTAL_VALUE_LOCKED: "Total value locked",
        A.WEEKLY_SWAP_VOLUME: "Weekly swap volume",
        A.WEEKLY_PROTOCOL_REVENUE_USD: "Weekly protocol revenue",
        A.WEEKLY_AFFILIATE_REVENUE_USD: "Weekly affiliate revenue",

        A.TRADE_BALANCE_TOTAL_USD: "Total trade account balance",
        A.TRADE_ASSET_HOLDERS_COUNT: "Trade asset holders",
        A.TRADE_ASSET_LARGEST_DEPOSIT: "Largest trade asset deposit",
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
            msg += f"RUNE is now the <b>#{milestone_str}</b> coin by market cap!"
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
