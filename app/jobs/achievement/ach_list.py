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
    DAILY_VOLUME = 'daily_volume'  # todo

    BLOCK_NUMBER = 'block_number'
    ANNIVERSARY = 'anniversary'

    SWAP_COUNT_TOTAL = 'swap_count_total'
    SWAP_COUNT_24H = 'swap_count_24h'
    SWAP_COUNT_30D = 'swap_count_30d'

    SWAP_VOLUME_TOTAL_RUNE = 'swap_volume_total_rune'

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

    POL_VALUE_RUNE = 'pol_value_rune'

    MAX_ADD_AMOUNT_USD_PER_POOL = 'max_add_amount_usd_per_pool'

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
    TRADE_ASSET_SWAPS_COUNT = 'trade_asset_swaps_count'
    TRADE_ASSET_SWAPS_VOLUME = 'trade_asset_swaps_volume'
    TRADE_ASSET_MOVE_COUNT = 'trade_asset_move_count'
    TRADE_ASSET_LARGEST_DEPOSIT = 'trade_asset_largest_deposit'

    @classmethod
    def all_keys(cls):
        return [getattr(cls, k) for k in cls.__dict__
                if not k.startswith('_') and k.upper() == k]


A = AchievementName

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
            v = provider.next(self.value)
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
BG_REVENUE = 'nn_wreath_revenue.png'
BG_BURN = 'nn_wreath_burnt.png'  # kept for a burnt RUNE achievement, none uses it yet
BG_VAULT = 'nn_wreath_vault.png'
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
    ADesc(A.DAILY_VOLUME, 'Daily volume', prefix='$', background=BG_SWAPS),
    ADesc(A.TOTAL_ACTIVE_BOND, 'Total active bond', postfix=POSTFIX_RUNE, background=BG_NETWORK),
    ADesc(A.TOTAL_BOND, 'Total bond', postfix=POSTFIX_RUNE, background=BG_NETWORK),
    ADesc(A.NODE_COUNT, 'Total node count', more_than=False, background=BG_NETWORK),
    ADesc(A.ACTIVE_NODE_COUNT, 'Active node count', more_than=False, background=BG_NETWORK),

    ADesc(A.ANNIVERSARY, 'Anniversary', more_than=False,
          background=BG_ANNIVERSARY,
          number_font=NUMBER_FONT_BALLOON,
          tint='#f4e18d',
          milestone_scale=MILESTONES_EVERY_INT,
          thresholds=1),

    ADesc(A.BLOCK_NUMBER, 'Blocks produced', milestone_scale=MILESTONES_EVERY_DIGIT,
          thresholds=7_000_000, background=BG_NETWORK),
    ADesc(A.DAILY_TX_COUNT, 'Daily transactions', background=BG_SWAPS),
    ADesc(A.TOTAL_MIMIR_VOTES, 'Total Mimir votes', more_than=False, background=BG_NETWORK),
    ADesc(A.MARKET_CAP_USD, 'RUNE market cap', prefix='$', background=BG_RUNE),
    ADesc(A.TOTAL_POOLS, 'Total pools', more_than=False),
    ADesc(A.TOTAL_ACTIVE_POOLS, 'Active pools', more_than=False),

    ADesc(A.SWAP_VOLUME_TOTAL_RUNE, 'Total swap volume', postfix=POSTFIX_RUNE, background=BG_SWAPS),

    ADesc(A.MAX_SWAP_AMOUNT_USD, 'Largest single swap', prefix='$',
          thresholds=1_329_208, background=BG_SWAPS),
    ADesc(A.MAX_ADD_AMOUNT_USD, 'Largest single liquidity add', prefix='$',
          thresholds=32_788_247),

    ADesc(A.MAX_ADD_AMOUNT_USD_PER_POOL, 'Largest ::asset:: liquidity add', prefix='$',
          thresholds={
              'ETH.THOR-0XA5F2211B9B8170F694421F2046281775E8468044': 32788247, 'BTC.BTC': 8143923,
              'ETH.ETH': 7454157,
              'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48': 3605512,
              'ETH.FOX-0XC770EEFAD204B5180DF6A14EE197D99D808EE52D': 3212391,
              'ETH.ALCX-0XDBDB4D16EDA451D0503B854CF79D55697F90C8DF': 3194501,
              'ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C': 3187722,
              'ETH.WBTC-0X2260FAC5E5542A773AA44FBCFEDF7C193BC2C599': 2556272,
              'ETH.YFI-0X0BC529C00C6401AEF6D220BE8C6EA1667F6AD93E': 2224691,
              'ETH.DODO-0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD': 2182393, 'BNB.BNB': 2032700,
              'ETH.DAI-0X6B175474E89094C44DA98B954EEDEAC495271D0F': 1996651,
              'ETH.SUSHI-0X6B3595068778DD592E39A122F4F5A5CF09C90FE2': 1824522,
              'DOGE.DOGE': 1719463,
              'ETH.XDEFI-0X72B886D09C117654AB7DA13A14D603001DE0B777': 1202132,
              'GAIA.ATOM': 1166449, 'ETH.KYL-0X67B6D479C7BB412C54E03DCA8E1BC6740CE6B99C': 1043058,
              'BCH.BCH': 906185,
              'ETH.RAZE-0X5EAA69B29F99C84FE5DE8200340B4E9B4AB38EAC': 840815,
              'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7': 773030,
              'ETH.UOS-0XD13C7342E1EF687C5AD21B27C2B65D772CAB5C8C': 724606, 'LTC.LTC': 676559,
              'ETH.PERP-0XBC396689893D065F41BC2C6ECBEE5E0085233447': 559955,
              'ETH.ALPHA-0XA1FAA113CBE53436DF28FF0AEE54275C13B40975': 513128,
              'ETH.CREAM-0X2BA592F78DB6436527729929AAF6C908497CB200': 456243,
              'ETH.AAVE-0X7FC66500C84A76AD7E9C93437BFC5AC33E2DDAE9': 375400,
              'ETH.TGT-0X108A850856DB3F85D0269A2693D896B394C80325': 318765,
              'ETH.SNX-0XC011A73EE8576FB46F5E1C5751CA3B9FE0AF2A6F': 249224,
              'ETH.HEGIC-0X584BC13C7D411C00C01A62E8019472DE68768430': 225752,
              'AVAX.AVAX': 140236,
              'ETH.TVK-0XD084B83C305DAFD76AE3E1B4E1F1FE2ECCCB3988': 113558,
              'AVAX.USDC-0XB97EF9EF8734C71904D8002F8B6BC66DD9C48A6E': 53465,
              'ETH.GUSD-0X056FD409E1D7A124BD7017459DFEA2F387B6D5CD': 40480,
              'ETH.DNA-0XEF6344DE1FCFC5F48C30234C16C1389E8CDC572C': 30343,
              'ETH.LINK-0X514910771AF9CA656AF840DFF83E8264ECF986CA': 29474,
              'AVAX.USDT-0X9702230A8EA53601F5CD2DC00FDBC13D4DF4A8C7': 46,
              'ETH.CRV-0XD533A949740BB3306D119CC777FA900BA034CD52': 7
          }),

    ADesc(A.COIN_MARKET_CAP_RANK, 'By market cap', milestone_scale=MILESTONES_EVERY_INT,
          thresholds=42, more_than=False, background=BG_RUNE),

    ADesc(A.POL_VALUE_RUNE, 'POL value', postfix=POSTFIX_RUNE, background=BG_VAULT),

    ADesc(A.BTC_IN_VAULT, 'Bitcoin in vaults', background=BG_BTC),
    ADesc(A.ETH_IN_VAULT, 'Ethereum in vaults', background=BG_ETH),
    ADesc(A.STABLES_IN_VAULT, 'Stablecoins in vaults', background=BG_VAULT),

    ADesc(A.TOTAL_VALUE_LOCKED, 'Total value locked', prefix='$', thresholds=356_700_000, background=BG_VAULT),
    ADesc(A.WEEKLY_SWAP_VOLUME, 'Weekly swap volume', prefix='$', thresholds=300_600_000, background=BG_SWAPS),
    ADesc(A.WEEKLY_PROTOCOL_REVENUE_USD, 'Weekly protocol revenue', prefix='$', thresholds=867_900,
          background=BG_REVENUE),
    ADesc(A.WEEKLY_AFFILIATE_REVENUE_USD, 'Weekly affiliate revenue', prefix='$', thresholds=60_300,
          background=BG_REVENUE),

    # trade assets
    ADesc(A.TRADE_BALANCE_TOTAL_USD, 'Total trade account balance', prefix='$', thresholds=10_000_000,
          background=BG_VAULT),
    ADesc(A.TRADE_ASSET_HOLDERS_COUNT, 'Trade asset holders', thresholds=100, background=BG_USERS),
    ADesc(A.TRADE_ASSET_SWAPS_COUNT, 'Trade asset swaps', thresholds=100_000, background=BG_SWAPS),
    ADesc(A.TRADE_ASSET_MOVE_COUNT, 'Trade account deposits & withdrawals', thresholds=10_000, background=BG_SWAPS),
    ADesc(A.TRADE_ASSET_LARGEST_DEPOSIT, 'Largest trade asset deposit', prefix='$', thresholds=100_000,
          background=BG_VAULT),
    ADesc(A.TRADE_ASSET_SWAPS_VOLUME, 'Trade asset swap volume', prefix='$', thresholds=1_000_000,
          background=BG_SWAPS),
]}
