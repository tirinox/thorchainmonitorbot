import math
from typing import NamedTuple, Union, Optional

from jobs.achievement.milestones import Milestones, MilestonesEveryInt
from lib.money import RAIDO_GLYPH

POSTFIX_RUNE = RAIDO_GLYPH
META_KEY_SPEC = '::asset::'
ACH_CUT_OFF_TS = 1674473134.216954


class AchievementName:
    # Test & debug:
    TEST = '__test'
    TEST_SPEC = '__test_sp'
    TEST_DESCENDING = '__test_desc'

    # Real:
    DAU = 'dau'
    MAU = 'mau'
    WALLET_COUNT = 'wallet_count'

    DAILY_TX_COUNT = 'daily_tx_count'  # todo
    DAILY_VOLUME = 'daily_volume'
    MONTHLY_SWAP_VOLUME = 'monthly_swap_volume'

    BLOCK_NUMBER = 'block_number'
    ANNIVERSARY = 'anniversary'

    SWAP_COUNT_TOTAL = 'swap_count_total'
    SWAP_COUNT_24H = 'swap_count_24h'
    SWAP_COUNT_30D = 'swap_count_30d'

    SWAP_VOLUME_TOTAL_USD = 'swap_volume_total_usd'

    ADD_LIQUIDITY_COUNT_TOTAL = 'add_liquidity_count_total'
    ADD_LIQUIDITY_VOLUME_TOTAL = 'add_liquidity_volume_total'

    NODE_COUNT = 'node_count'
    ACTIVE_NODE_COUNT = 'active_node_count'
    TOTAL_ACTIVE_BOND = 'total_active_bond'
    TOTAL_BOND = 'total_bond'

    TOTAL_MIMIR_VOTES = 'total_mimir_votes'

    MARKET_CAP_USD = 'market_cap_usd'
    TOTAL_POOLS = 'total_pools'
    TOTAL_ACTIVE_POOLS = 'total_active_pools'

    COIN_MARKET_CAP_RANK = 'coin_market_cap_rank'

    MAX_SWAP_AMOUNT_USD = 'max_swap_amount_usd'
    MAX_ADD_AMOUNT_USD = 'max_add_amount_usd'

    POL_VALUE_USD = 'pol_value_usd'


    # from weekly chart:
    BTC_IN_VAULT = 'btc_in_vault'
    ETH_IN_VAULT = 'eth_in_vault'
    STABLES_IN_VAULT = 'stables_in_vault'
    TOTAL_VALUE_LOCKED = 'tvl'
    WEEKLY_PROTOCOL_REVENUE_USD = 'weekly_protocol_revenue_usd'
    WEEKLY_AFFILIATE_REVENUE_USD = 'weekly_affiliate_revenue_usd'
    WEEKLY_SWAP_VOLUME = 'weekly_swap_volume'

    # trade assets
    TRADE_BALANCE_TOTAL_USD = 'trade_balance_total_usd'
    TRADE_ASSET_HOLDERS_COUNT = 'trade_asset_holders_count'
    TRADE_ASSET_LARGEST_DEPOSIT = 'trade_asset_largest_deposit'

    @classmethod
    def all_keys(cls):
        return [getattr(cls, k) for k in cls.__dict__
                if not k.startswith('_') and k.upper() == k]


A = AchievementName

# records of a single event: a feed carries the largest one of a batch, not a current level of anything
SINGLE_EVENT_KEYS = {
    A.MAX_SWAP_AMOUNT_USD, A.MAX_ADD_AMOUNT_USD, A.TRADE_ASSET_LARGEST_DEPOSIT,
}

MILESTONES_NORMAL = Milestones()
MILESTONES_EVERY_DIGIT = Milestones(Milestones.EVERY_DIGIT_PROGRESSION)
MILESTONES_EVERY_INT = MilestonesEveryInt()


class EventTestAchievement(NamedTuple):
    value: int
    specialization: str = ''
    descending: bool = False


class Achievement(NamedTuple):
    key: str
    value: int  # real current value
    milestone: int = 0  # current milestone
    timestamp: float = 0
    prev_milestone: int = 0
    previous_ts: float = 0
    specialization: str = ''
    descending: bool = False  # if True, then we need to check if value is less than milestone
    last_seen_ts: float = 0  # the last time this metric was fed to the tracker; 0 for records saved before it
    silent: bool = False  # the milestone was saved without a message (a catch-up after an outage)

    @property
    def has_previous(self):
        return self.prev_milestone > 0 and self.previous_ts > ACH_CUT_OFF_TS

    @property
    def descriptor(self) -> 'AchievementDescription':
        return ACHIEVEMENT_DESC_MAP[self.key]

    def get_previous_milestone(self):
        provider: Milestones = self.descriptor.milestone_scale
        if not provider:
            raise Exception(f'No description for achievement: {self.key!r}')

        if self.descending:
            # the lowest milestone not below the value: rank 29 is milestone 29, and 50 is already "top 50"
            v = provider.next(math.ceil(self.value) - 1)
        else:
            v = provider.previous(self.value)

        return v

    def get_next_milestone(self):
        # the goal after this one; 0 if a descending sequence has nowhere to go (e.g. rank #1)
        provider: Milestones = self.descriptor.milestone_scale
        if self.descending:
            return provider.previous(self.value - 1) if self.value > 1 else 0
        else:
            return provider.next(self.value)


# Card backgrounds (data/renderer/static/img/achievement/bg): one per category,
# so the same kind of metric always looks the same
BG_LIQUIDITY = 'nn_wreath_liquidity.png'
BG_NETWORK = 'nn_wreath_network.png'
BG_SWAPS = 'nn_wreath_swaps.png'
BG_USERS = 'nn_wreath_users.png'
BG_RUNE = 'nn_wreath_rune.png'
BG_REVENUE = 'nn_wreath_revenue_toast.png'
BG_AFFILIATE = 'nn_wreath_affiliate_grip.png'
BG_BURN = 'nn_wreath_burnt.png'  # kept for a burnt RUNE achievement, none uses it yet
BG_VAULT = 'nn_wreath_vault.png'
BG_STABLES = 'nn_wreath_stables_chains.png'
BG_TRADE = 'nn_wreath_trade.png'
BG_POL = 'nn_wreath_pol_roots.png'
BG_NODES = 'nn_wreath_nodes_fleet.png'
BG_BTC = 'nn_wreath_btc_vault_2.png'
BG_ETH = 'nn_wreath_eth_vault_2.png'
BG_ANNIVERSARY = 'nn_wreath_ann_3.png'

NUMBER_FONT_RUNIC = 'runic'
NUMBER_FONT_BALLOON = 'balloon'


class AchievementDescription(NamedTuple):
    key: str
    description: str
    postfix: str = ''
    prefix: str = ''
    url: str = ''  # url to the dashboard
    signed: bool = False
    more_than: bool = True
    background: str = BG_LIQUIDITY
    number_font: str = NUMBER_FONT_RUNIC
    milestone_scale: Milestones = MILESTONES_NORMAL
    thresholds: Union[int, dict] = 0
    tint: Optional[str] = None  # overrides the glow color of the background
    # its source feeds it only while it is news, so the tracker neither holds it as stale nor needs a first record
    always_fresh: bool = False
    # False turns an achievement off: the tracker ignores its feeds and keeps its record as it is
    enabled: bool = True


ADesc = AchievementDescription

ACHIEVEMENT_DESC_MAP = {a.key: a for a in [
    # each description will be replaced with the translation from the localization,
    # here they are just for convenience
    ADesc(A.TEST, 'Test metric'),
    ADesc(A.TEST_SPEC, 'Test metric', postfix=POSTFIX_RUNE),
    ADesc(A.TEST_DESCENDING, 'Test descending'),

    ADesc(A.DAU, 'Daily active users', thresholds=300, background=BG_USERS),
    ADesc(A.MAU, 'Monthly active users', thresholds=6500, background=BG_USERS),
    ADesc(A.WALLET_COUNT, 'Wallets', milestone_scale=MILESTONES_EVERY_DIGIT,
          thresholds=61000, background=BG_USERS),
    ADesc(A.SWAP_COUNT_TOTAL, 'Total swaps', background=BG_SWAPS),
    ADesc(A.SWAP_COUNT_24H, 'Swaps in 24h', background=BG_SWAPS),
    ADesc(A.SWAP_COUNT_30D, 'Monthly swaps', background=BG_SWAPS),

    ADesc(A.ADD_LIQUIDITY_COUNT_TOTAL, 'Liquidity additions'),
    ADesc(A.ADD_LIQUIDITY_VOLUME_TOTAL, 'Total liquidity added', postfix=POSTFIX_RUNE),
    # swap volumes in USD from Midgard's swap history: the last whole day, the last 30 whole days, all of it
    ADesc(A.DAILY_VOLUME, 'Daily swap volume', prefix='$', thresholds=50_000_000, background=BG_TRADE),
    ADesc(A.MONTHLY_SWAP_VOLUME, 'Monthly swap volume', prefix='$', thresholds=1_000_000_000,
          background=BG_TRADE),
    ADesc(A.TOTAL_ACTIVE_BOND, 'Total active bond', postfix=POSTFIX_RUNE, background=BG_NETWORK),
    ADesc(A.TOTAL_BOND, 'Total bond', postfix=POSTFIX_RUNE, background=BG_NETWORK),
    ADesc(A.NODE_COUNT, 'Total node count', more_than=False, background=BG_NETWORK, enabled=False),
    ADesc(A.ACTIVE_NODE_COUNT, 'Active node count', more_than=False, background=BG_NODES),

    ADesc(A.ANNIVERSARY, 'Anniversary', more_than=False,
          background=BG_ANNIVERSARY,
          number_font=NUMBER_FONT_BALLOON,
          milestone_scale=MILESTONES_EVERY_INT,
          thresholds=1,
          always_fresh=True),  # fed only within ANNIVERSARY_WINDOW, a year after the previous feed

    ADesc(A.BLOCK_NUMBER, 'Blocks produced', milestone_scale=MILESTONES_EVERY_DIGIT,
          thresholds=7_000_000, background=BG_NETWORK),
    ADesc(A.DAILY_TX_COUNT, 'Daily transactions', background=BG_SWAPS),
    ADesc(A.TOTAL_MIMIR_VOTES, 'Total Mimir votes', more_than=False, background=BG_NETWORK),
    ADesc(A.MARKET_CAP_USD, 'RUNE market cap', prefix='$', background=BG_RUNE),
    ADesc(A.TOTAL_POOLS, 'Total pools', more_than=False),
    ADesc(A.TOTAL_ACTIVE_POOLS, 'Active pools', more_than=False),

    ADesc(A.SWAP_VOLUME_TOTAL_USD, 'Total swap volume', prefix='$', milestone_scale=MILESTONES_EVERY_DIGIT,
          thresholds=100_000_000_000, background=BG_TRADE),

    ADesc(A.MAX_SWAP_AMOUNT_USD, 'Largest single swap', prefix='$',
          thresholds=1_329_208, background=BG_SWAPS),
    ADesc(A.MAX_ADD_AMOUNT_USD, 'Largest single liquidity add', prefix='$',
          thresholds=32_788_247),

    ADesc(A.COIN_MARKET_CAP_RANK, 'By market cap', milestone_scale=MILESTONES_EVERY_INT,
          thresholds=42, more_than=False, background=BG_RUNE),

    ADesc(A.POL_VALUE_USD, 'POL value', prefix='$', background=BG_POL),

    ADesc(A.BTC_IN_VAULT, 'Bitcoin in vaults', background=BG_BTC),
    ADesc(A.ETH_IN_VAULT, 'Ethereum in vaults', background=BG_ETH),
    ADesc(A.STABLES_IN_VAULT, 'Stablecoins in vaults', prefix='$', background=BG_STABLES),

    ADesc(A.TOTAL_VALUE_LOCKED, 'Total value locked', prefix='$', thresholds=356_700_000, background=BG_VAULT),
    ADesc(A.WEEKLY_SWAP_VOLUME, 'Weekly swap volume', prefix='$', thresholds=300_600_000, background=BG_TRADE),
    ADesc(A.WEEKLY_PROTOCOL_REVENUE_USD, 'Weekly protocol revenue', prefix='$', thresholds=867_900,
          background=BG_REVENUE),
    ADesc(A.WEEKLY_AFFILIATE_REVENUE_USD, 'Weekly affiliate revenue', prefix='$', thresholds=60_300,
          background=BG_AFFILIATE),

    # trade assets
    ADesc(A.TRADE_BALANCE_TOTAL_USD, 'Total trade account balance', prefix='$', thresholds=10_000_000,
          background=BG_TRADE),
    ADesc(A.TRADE_ASSET_HOLDERS_COUNT, 'Trade asset holders', thresholds=100, background=BG_TRADE),
    ADesc(A.TRADE_ASSET_LARGEST_DEPOSIT, 'Largest trade asset deposit', prefix='$', thresholds=100_000,
          background=BG_TRADE),
]}
