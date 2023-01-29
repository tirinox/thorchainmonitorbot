from typing import NamedTuple

ACH_CUT_OFF_TS = 1674473134.216954


class Achievement(NamedTuple):
    key: str
    value: int  # real current value
    milestone: int = 0  # current milestone
    timestamp: float = 0
    prev_milestone: int = 0
    previous_ts: float = 0
    specialization: str = ''
    descending: bool = False  # if True, then we need to check if value is less than milestone

    # --- KEYS ---

    TEST = '__test'
    TEST_SPEC = '__test_sp'

    DAU = 'dau'
    MAU = 'mau'
    WALLET_COUNT = 'wallet_count'

    DAILY_TX_COUNT = 'daily_tx_count'  # todo
    DAILY_VOLUME = 'daily_volume'  # todo
    BLOCK_NUMBER = 'block_number'
    ANNIVERSARY = 'anniversary'

    SWAP_COUNT_TOTAL = 'swap_count_total'
    SWAP_COUNT_24H = 'swap_count_24h'
    SWAP_COUNT_30D = 'swap_count_30d'
    SWAP_UNIQUE_COUNT = 'swap_unique_count'
    SWAP_VOLUME_TOTAL_RUNE = 'swap_volume_total_rune'

    ADD_LIQUIDITY_COUNT_TOTAL = 'add_liquidity_count_total'
    ADD_LIQUIDITY_VOLUME_TOTAL = 'add_liquidity_volume_total'

    ILP_PAID_TOTAL = 'ilp_paid_total'

    NODE_COUNT = 'node_count'
    ACTIVE_NODE_COUNT = 'active_node_count'
    TOTAL_ACTIVE_BOND = 'total_active_bond'
    TOTAL_BOND = 'total_bond'

    TOTAL_MIMIR_VOTES = 'total_mimir_votes'

    MARKET_CAP_USD = 'market_cap_usd'
    TOTAL_POOLS = 'total_pools'
    TOTAL_ACTIVE_POOLS = 'total_active_pools'

    TOTAL_UNIQUE_SAVERS = 'total_unique_savers'
    TOTAL_SAVED_USD = 'total_saved_usd'
    TOTAL_SAVERS_EARNED_USD = 'total_savers_earned_usd'

    SAVER_VAULT_SAVED_USD = 'saver_vault_saved_usd'
    SAVER_VAULT_SAVED_ASSET = 'saver_vault_saved_asset'
    SAVER_VAULT_MEMBERS = 'saver_vault_members'
    SAVER_VAULT_EARNED_ASSET = 'saver_vault_earned_asset'

    # COIN_MARKET_CAP_RANK = 'coin_market_cap_rank'

    MAX_SWAP_AMOUNT_USD = 'max_swap_amount_usd'

    @classmethod
    def all_keys(cls):
        return [getattr(cls, k) for k in cls.__dict__
                if not k.startswith('_') and k.upper() == k]

    @property
    def has_previous(self):
        return self.prev_milestone > 0 and self.previous_ts > ACH_CUT_OFF_TS


A = Achievement

# every single digit is a milestone
GROUP_EVERY_1 = {
    A.BLOCK_NUMBER,
    A.ANNIVERSARY,
    A.WALLET_COUNT,
    # A.COIN_MARKET_CAP_RANK,
}

# this metrics only trigger when greater than their minimums
GROUP_MINIMALS = {
    A.DAU: 300,
    A.MAU: 6500,
    A.WALLET_COUNT: 61000,
    A.BLOCK_NUMBER: 7_000_000,
    A.ANNIVERSARY: 1,
    A.MAX_SWAP_AMOUNT_USD: 1_329_208.3072876,
    # A.COIN_MARKET_CAP_RANK: 42,
}


class AchievementTest(NamedTuple):
    value: int
    specialization: str = ''
