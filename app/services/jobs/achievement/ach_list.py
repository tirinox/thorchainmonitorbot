from typing import NamedTuple, Union, Tuple, List

from services.jobs.achievement.milestones import Milestones, MilestonesEveryInt
from services.lib.money import RAIDO_GLYPH, short_money

POSTFIX_RUNE = RAIDO_GLYPH
META_KEY_SPEC = '::asset::'
ACH_CUT_OFF_TS = 1674473134.216954


class AchievementName:
    # --- KEYS ---

    TEST = '__test'
    TEST_SPEC = '__test_sp'
    TEST_DESCENDING = '__test_desc'

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

    COIN_MARKET_CAP_RANK = 'coin_market_cap_rank'

    MAX_SWAP_AMOUNT_USD = 'max_swap_amount_usd'
    MAX_ADD_AMOUNT_USD = 'max_add_amount_usd'

    POL_VALUE_RUNE = 'pol_value_rune'

    MAX_ADD_AMOUNT_USD_PER_POOL = 'max_add_amount_usd_per_pool'

    # new:
    BTC_IN_VAULT = 'btc_in_vault'
    ETH_IN_VAULT = 'eth_in_vault'
    STABLES_IN_VAULT = 'stables_in_vault'

    @classmethod
    def all_keys(cls):
        return [getattr(cls, k) for k in cls.__dict__
                if not k.startswith('_') and k.upper() == k]


A = AchievementName

MILESTONES_NORMAL = Milestones()
MILESTONES_EVERY_DIGIT = Milestones(Milestones.EVERY_DIGIT_PROGRESSION)
MILESTONES_EVERY_INT = MilestonesEveryInt()

# special groups
GROUP_MILESTONES = {
    A.BLOCK_NUMBER: MILESTONES_EVERY_DIGIT,
    A.ANNIVERSARY: MILESTONES_EVERY_INT,
    A.WALLET_COUNT: MILESTONES_EVERY_DIGIT,
    A.COIN_MARKET_CAP_RANK: MILESTONES_EVERY_INT,
}

# this metrics only trigger when greater than their historic maximums
GROUP_MINIMALS = {
    A.DAU: 300,
    A.MAU: 6500,
    A.WALLET_COUNT: 61000,
    A.BLOCK_NUMBER: 7_000_000,
    A.ANNIVERSARY: 1,

    A.MAX_SWAP_AMOUNT_USD: 1_329_208,
    A.MAX_ADD_AMOUNT_USD: 32_788_247,  # fixme: debug

    A.MAX_ADD_AMOUNT_USD_PER_POOL: {
        'ETH.THOR-0XA5F2211B9B8170F694421F2046281775E8468044': 32788247, 'BTC.BTC': 8143923,
        'ETH.ETH': 7454157, 'BNB.BUSD-BD1': 6000816, 'TERRA.LUNA': 5600484,
        'TERRA.UST': 4970527,
        'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48': 3605512,
        'ETH.FOX-0XC770EEFAD204B5180DF6A14EE197D99D808EE52D': 3212391,
        'ETH.ALCX-0XDBDB4D16EDA451D0503B854CF79D55697F90C8DF': 3194501,
        'ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C': 3187722,
        'ETH.WBTC-0X2260FAC5E5542A773AA44FBCFEDF7C193BC2C599': 2556272,
        'BNB.ETH-1C9': 2403972, 'BNB.BTCB-1DE': 2367850,
        'ETH.YFI-0X0BC529C00C6401AEF6D220BE8C6EA1667F6AD93E': 2224691,
        'ETH.DODO-0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD': 2182393, 'BNB.BNB': 2032700,
        'ETH.DAI-0X6B175474E89094C44DA98B954EEDEAC495271D0F': 1996651,
        'ETH.SUSHI-0X6B3595068778DD592E39A122F4F5A5CF09C90FE2': 1824522,
        'DOGE.DOGE': 1719463,
        'ETH.XDEFI-0X72B886D09C117654AB7DA13A14D603001DE0B777': 1202132,
        'GAIA.ATOM': 1166449, 'ETH.KYL-0X67B6D479C7BB412C54E03DCA8E1BC6740CE6B99C': 1043058,
        'BCH.BCHBCH.BCHBCH.BCHBCH.BCHBCH.BCHB2': 906185,
        'ETH.RAZE-0X5EAA69B29F99C84FE5DE8200340B4E9B4AB38EAC': 840815,
        'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7': 773030,
        'ETH.UOS-0XD13C7342E1EF687C5AD21B27C2B65D772CAB5C8C': 724606, 'LTC.LTC': 676559,
        'ETH.PERP-0XBC396689893D065F41BC2C6ECBEE5E0085233447': 559955,
        'ETH.ALPHA-0XA1FAA113CBE53436DF28FF0AEE54275C13B40975': 513128,
        'ETH.CREAM-0X2BA592F78DB6436527729929AAF6C908497CB200': 456243,
        'ETH.AAVE-0X7FC66500C84A76AD7E9C93437BFC5AC33E2DDAE9': 375400,
        'ETH.TGT-0X108A850856DB3F85D0269A2693D896B394C80325': 318765, 'BNB.AVA-645': 284028,
        'ETH.SNX-0XC011A73EE8576FB46F5E1C5751CA3B9FE0AF2A6F': 249224, 'BNB.TWT-8C2': 229859,
        'ETH.HEGIC-0X584BC13C7D411C00C01A62E8019472DE68768430': 225752,
        'BNB.CAS-167': 140345, 'AVAX.AVAX': 140236,
        'ETH.TVK-0XD084B83C305DAFD76AE3E1B4E1F1FE2ECCCB3988': 113558,
        'AVAX.USDC-0XB97EF9EF8734C71904D8002F8B6BC66DD9C48A6E': 53465,
        'BNB.NEXO-A84': 52778, 'BNB.ADA-9F4': 43730,
        'ETH.GUSD-0X056FD409E1D7A124BD7017459DFEA2F387B6D5CD': 40480, 'BNB.FTM-A64': 36010,
        'ETH.DNA-0XEF6344DE1FCFC5F48C30234C16C1389E8CDC572C': 30343,
        'ETH.LINK-0X514910771AF9CA656AF840DFF83E8264ECF986CA': 29474, 'BNB.FRM-DE7': 28985,
        'BNB.USDT-6D8': 24966, 'BNB.DOT-64C': 11981, 'BNB.AERGO-46B': 504,
        'BNB.XRP-BF2': 235, 'BNB.BULL-BE4': 98, 'BNB.ETHBULL-D33': 67,
        'AVAX.USDT-0X9702230A8EA53601F5CD2DC00FDBC13D4DF4A8C7': 46, 'BNB.CAKE-435': 36,
        'BNB.EQL-586': 32, 'BNB.EVT-49B': 26, 'BNB.SLV-986': 10, 'BNB.AWC-986': 9,
        'ETH.CRV-0XD533A949740BB3306D119CC777FA900BA034CD52': 7
    },

    A.SAVER_VAULT_MEMBERS: {
        'BUSD': 50,
        'USDT': 50,
        'USDC': 50,
        'TUSD': 50,
        'PUSD': 50,
    },

    A.SAVER_VAULT_SAVED_USD: {
        'BUSD': 10_000,
        'USDT': 10_000,
        'USDC': 10_000,
        'TUSD': 10_000,
        'PUST': 10_000,
    },

    A.SAVER_VAULT_SAVED_ASSET: {
        'BUSD': 10_000,
        'USDT': 10_000,
        'USDC': 10_000,
        'TUSD': 10_000,
        'PUST': 10_000,
    },

    A.SAVER_VAULT_EARNED_ASSET: {
        'BUSD': 1_000,
        'USDT': 1_000,
        # 'USDC': 1_000,
        'TUSD': 1_000,
        'PUST': 1_000,
    },

    A.COIN_MARKET_CAP_RANK: 42,
}


class AchievementTest(NamedTuple):
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

    def get_previous_milestone(self):
        provider = GROUP_MILESTONES.get(self.key, MILESTONES_NORMAL)

        if self.descending:
            v = provider.next(self.value)
        else:
            v = provider.previous(self.value)

        return v


class AchievementDescription(NamedTuple):
    key: str
    description: str
    postfix: str = ''
    prefix: str = ''
    url: str = ''  # url to the dashboard
    signed: bool = False
    more_than: bool = True
    preferred_bg: Union[Tuple, List, str] = None
    custom_attributes: dict = None

    @property
    def image(self):
        return f'ach_{self.key}.png'

    @staticmethod
    def space_before_non_empty(s):
        return f' {s}' if s else ''

    @classmethod
    def _do_substitutions(cls, achievement: Achievement, text: str) -> str:
        return text.replace(META_KEY_SPEC, achievement.specialization)

    def format_value(self, value, ach: Achievement):
        return short_money(value,
                           prefix=self._do_substitutions(ach, self.prefix),
                           postfix=self.space_before_non_empty(self._do_substitutions(ach, self.postfix)),
                           integer=True, signed=self.signed)


ADesc = AchievementDescription

SAVER_BG = 'nn_wreath_saver.png'
BTC_BG = 'nn_wreath_btc_vault.png'
ETH_BG = 'nn_wreath_eth_vault.png'
ANNIVERSARY_BG = 'nn_wreath_ann_2.png'

ACHIEVEMENT_DESC_MAP = {a.key: a for a in [
    # each description will be replaced with the translation from the localization,
    # here they are just for convenience
    ADesc(A.TEST, 'Test metric'),
    ADesc(A.TEST_SPEC, 'Test metric', postfix=POSTFIX_RUNE),
    ADesc(A.TEST_DESCENDING, 'Test descending'),

    ADesc(A.DAU, 'Daily active users'),
    ADesc(A.MAU, 'Monthly active users'),
    ADesc(A.WALLET_COUNT, 'Number of wallets'),
    ADesc(A.SWAP_COUNT_TOTAL, 'Total swap count'),
    ADesc(A.SWAP_COUNT_24H, '24h swap count'),
    ADesc(A.SWAP_COUNT_30D, 'Monthly swap count'),

    ADesc(A.ADD_LIQUIDITY_COUNT_TOTAL, 'Times liquidity added'),
    ADesc(A.ADD_LIQUIDITY_VOLUME_TOTAL, 'Total add liquidity volume'),
    ADesc(A.DAILY_VOLUME, 'Daily volume', prefix='$'),
    ADesc(A.ILP_PAID_TOTAL, 'Total ILP paid', postfix=POSTFIX_RUNE),
    ADesc(A.TOTAL_ACTIVE_BOND, 'Total active bond'),
    ADesc(A.TOTAL_BOND, 'Total bond', postfix=POSTFIX_RUNE),
    ADesc(A.NODE_COUNT, 'Total nodes count', more_than=False),
    ADesc(A.ACTIVE_NODE_COUNT, 'Active nodes count', more_than=False),

    ADesc(A.ANNIVERSARY, 'Anniversary', more_than=False, preferred_bg=ANNIVERSARY_BG,
          custom_attributes={
              'main_font': 'custom_font_balloon',
              'desc_color': '#f4e18d',
              'desc_stroke': '#954c07',
              'main_area': (320, 320),
              'font_style': 'normal',
          }),

    ADesc(A.BLOCK_NUMBER, 'Blocks generated'),
    ADesc(A.DAILY_TX_COUNT, 'Daily TX count'),
    ADesc(A.TOTAL_MIMIR_VOTES, 'Total Mimir votes', more_than=False),
    ADesc(A.MARKET_CAP_USD, 'Rune Total Market Cap', prefix='$'),
    ADesc(A.TOTAL_POOLS, 'Total pools', more_than=False),
    ADesc(A.TOTAL_ACTIVE_POOLS, 'Active pools', more_than=False),

    ADesc(A.TOTAL_UNIQUE_SAVERS, 'Total unique savers', prefix=SAVER_BG),
    ADesc(A.TOTAL_SAVED_USD, 'Total USD saved', prefix='$', preferred_bg=SAVER_BG),
    ADesc(A.TOTAL_SAVERS_EARNED_USD, 'Savers: Total USD earned', prefix='$', preferred_bg=SAVER_BG),
    ADesc(A.SAVER_VAULT_SAVED_ASSET, '::asset:: Savers depth', preferred_bg=SAVER_BG),
    ADesc(A.SAVER_VAULT_SAVED_USD, '::asset:: Savers depth in USD', prefix='$', preferred_bg=SAVER_BG),
    ADesc(A.SAVER_VAULT_MEMBERS, '::asset:: savers count', preferred_bg=SAVER_BG),
    ADesc(A.SAVER_VAULT_EARNED_ASSET, 'Savers earned ::asset::', preferred_bg=SAVER_BG),

    ADesc(A.SWAP_VOLUME_TOTAL_RUNE, 'Total swap volume', postfix=POSTFIX_RUNE),

    ADesc(A.MAX_SWAP_AMOUNT_USD, 'Maximum swap volume', prefix='$'),
    ADesc(A.MAX_ADD_AMOUNT_USD, 'Maximum add liquidity volume', prefix='$'),

    ADesc(A.MAX_ADD_AMOUNT_USD_PER_POOL, 'Added ::asset:: in a single TX', prefix='$'),

    ADesc(A.COIN_MARKET_CAP_RANK, 'Market cap rank'),

    ADesc(A.POL_VALUE_RUNE, 'POL maximum value', preferred_bg=SAVER_BG),

    ADesc(A.BTC_IN_VAULT, 'Bitcoin in vaults', preferred_bg=BTC_BG),
    ADesc(A.ETH_IN_VAULT, 'Ethereum in vaults', preferred_bg=ETH_BG),
    ADesc(A.STABLES_IN_VAULT, 'Stable coins in vaults'),
]}
