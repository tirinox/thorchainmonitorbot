from typing import NamedTuple

from lib.date_utils import MINUTE

BTC_SYMBOL = 'BTC.BTC'

BCH_SYMBOL = 'BCH.BCH'

NATIVE_RUNE_SYMBOL = 'THOR.RUNE'
RUNE_SYMBOL = NATIVE_RUNE_SYMBOL

RUNE_SYMBOL_DET = 'RUNE-DET'
RUNE_SYMBOL_POOL = 'RUNE-MARKET'
RUNE_SYMBOL_CEX = 'RUNE-MARKET-CEX'
TCY_SYMBOL = 'THOR.TCY'

ETH_SYMBOL = 'ETH.ETH'

AVAX_SYMBOL = 'AVAX.AVAX'

ETH_USDT_TEST_SYMBOL = 'ETH.USDT-0XA3910454BF2CB59B8B3A401589A3BACC5CA42306'
ETH_USDT_SYMBOL = 'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7'
ETH_USDC_SYMBOL = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
ETH_DAI_SYMBOL = 'ETH.DAI-0X6B175474E89094C44DA98B954EEDEAC495271D0F'
AVAX_USDC_SYMBOL = 'AVAX.USDC-0XB97EF9EF8734C71904D8002F8B6BC66DD9C48A6E'
AVAX_USDT_SYMBOL = 'AVAX.USDT-0X9702230A8EA53601F5CD2DC00FDBC13D4DF4A8C7'
BSC_BUSD_SYMBOL = 'BSC.BUSD-0XE9E7CEA3DEDCA5984780BAFC599BD69ADD087D56'
BSC_USDC_SYMBOL = 'BSC.USDC-0X8AC76A51CC950D9822D68B83FE1AD97B32CD580D'
ETH_GUSD_SYMBOL = 'ETH.GUSD-0X056FD409E1D7A124BD7017459DFEA2F387B6D5CD'
ETH_LUSD_SYMBOL = 'ETH.LUSD-0X5F98805A4E8BE255A32880FDEC7F6728C6568BA0'

DOGE_SYMBOL = 'DOGE.DOGE'

RUNE_IDEAL_SUPPLY = 500_000_000
RUNE_SUPPLY_AFTER_SWITCH = 486_051_059
RUNE_BURNT_ADR_12 = 60_000_000

RUNE_DENOM = 'rune'

STABLE_COIN_POOLS_ALL = (
    BSC_BUSD_SYMBOL,
    ETH_USDC_SYMBOL,
    BSC_USDC_SYMBOL,
    AVAX_USDC_SYMBOL,
    AVAX_USDT_SYMBOL,
    ETH_USDT_SYMBOL,
    ETH_DAI_SYMBOL,
    ETH_GUSD_SYMBOL,
    ETH_LUSD_SYMBOL,
)

STABLE_COIN_POOLS = STABLE_COIN_POOLS_ALL

DEFAULT_CEX_NAME = 'Binance'
DEFAULT_CEX_BASE_ASSET = 'USDT'


def is_stable_coin(pool):
    return pool in STABLE_COIN_POOLS_ALL


class Chains:
    THOR = 'THOR'
    ETH = 'ETH'
    BTC = 'BTC'
    BCH = 'BCH'
    LTC = 'LTC'
    BNB = 'BNB'
    DOGE = 'DOGE'
    AVAX = 'AVAX'
    ATOM = 'GAIA'
    BSC = 'BSC'
    BASE = 'BASE'

    ALL_EVM = (ETH, BSC, BASE, AVAX)

    META_ALL = (THOR, ETH, BTC, BCH, LTC, BNB, DOGE, AVAX, ATOM, BSC, BASE)

    @staticmethod
    def detect_chain(orig_address: str) -> str:
        address = orig_address.lower()
        if address.startswith('0x'):
            return Chains.ETH  # or other EVM chain??
        elif address.startswith('thor') or address.startswith('tthor') or address.startswith('sthor'):
            return Chains.THOR
        elif address.startswith('bnb') or address.startswith('tbnb'):
            return Chains.BNB
        elif orig_address.startswith('D'):
            return Chains.DOGE
        elif address.startswith('cosmos'):
            return Chains.ATOM
        return ''

    @staticmethod
    def block_time_default(chain: str) -> float:
        if chain == Chains.ETH:
            return 13
        elif chain == Chains.BTC or chain == Chains.BCH:
            return 10 * MINUTE
        elif chain == Chains.LTC:
            return 2.5 * MINUTE
        elif chain == Chains.BNB:
            return 0.4
        elif chain == Chains.THOR:
            return THOR_BLOCK_TIME
        elif chain == Chains.DOGE:
            return MINUTE
        elif chain == Chains.ATOM:
            return 6.85
        elif chain == Chains.AVAX:
            return 3.0
        elif chain == Chains.BSC:
            return 3.0
        elif chain == Chains.BASE:
            return 2.0
        return 0.01

    @staticmethod
    def web3_chain_id(chain: str) -> int:
        if chain == Chains.ETH:
            return 0x1
        elif chain == Chains.AVAX:
            return 43114
        elif chain == Chains.BSC:
            return 56
        elif chain == Chains.BASE:
            return 8453
        return 0


class NetworkIdents:
    TESTNET_MULTICHAIN = 'testnet-multi'
    CHAOSNET_MULTICHAIN = 'chaosnet-multi'
    MAINNET = 'mainnet'
    STAGENET_MULTICHAIN = 'stagenet-multi'

    @classmethod
    def is_test(cls, network: str):
        return 'testnet' in network

    @classmethod
    def is_live(cls, network: str):
        return not cls.is_test(network)

    @classmethod
    def is_multi(cls, network: str):
        return 'multi' in network or network == cls.MAINNET


RUNE_DECIMALS = 8
THOR_DIVIDER = float(10 ** RUNE_DECIMALS)
THOR_DIVIDER_INV = 1.0 / THOR_DIVIDER

THOR_BLOCK_TIME = 6.0  # seconds. 10 blocks / minute
THOR_BLOCK_SPEED = 1 / THOR_BLOCK_TIME
THOR_BLOCKS_PER_MINUTE = MINUTE * THOR_BLOCK_SPEED

THOR_BASIS_POINT_MAX = 10_000


def bp_to_float(bp):
    return int(bp) / THOR_BASIS_POINT_MAX


def bp_to_percent(bp):
    return bp_to_float(bp) * 100.0


def thor_to_float(x) -> float:
    return int(x) * THOR_DIVIDER_INV


def float_to_thor(x: float) -> int:
    return int(x * THOR_DIVIDER)


class THORPort:
    class TestNet(NamedTuple):
        RPC = 26657
        P2P = 26656
        BIFROST = 6040
        BIFROST_P2P = 5040
        NODE = 1317

    class StageNet(NamedTuple):
        RPC = 26657
        P2P = 26656
        BIFROST = 6040
        BIFROST_P2P = 5040
        NODE = 1317

    class MainNet(NamedTuple):
        RPC = 27147
        P2P = 27146
        BIFROST = 6040
        BIFROST_P2P = 5040
        NODE = 1317

    FAMILIES = {
        NetworkIdents.TESTNET_MULTICHAIN: TestNet,
        NetworkIdents.STAGENET_MULTICHAIN: StageNet,
        NetworkIdents.MAINNET: MainNet,
        NetworkIdents.CHAOSNET_MULTICHAIN: MainNet,
    }

    @classmethod
    def get_port_family(cls, network_ident):
        return cls.FAMILIES.get(network_ident, cls.MainNet)


BLOCKS_PER_YEAR = 5_256_000

DEFAULT_KILL_RUNE_START_BLOCK = 6_500_000
DEFAULT_KILL_RUNE_DURATION_BLOCKS = BLOCKS_PER_YEAR

SAVERS_BEGIN_BLOCK = 8_195_056

HTTP_CLIENT_ID = 'thorinfobot'

THORCHAIN_BIRTHDAY = 1618058210955 * 0.001  # 2021-04-10T12:36:50.955991742Z

STAGENET_RESERVE_ADDRESS = 'sthor1dheycdevq39qlkxs2a6wuuzyn4aqxhvepe6as4'

DEFAULT_RUNE_FEE = 2000000

DEFAULT_RESERVE_ADDRESS = 'thor1dheycdevq39qlkxs2a6wuuzyn4aqxhve4qxtxt'
BOND_MODULE = 'thor17gw75axcnr8747pkanye45pnrwk7p9c3cqncsv'
POOL_MODULE = 'thor1g98cy3n9mmjrpn0sxmn63lztelera37n8n67c0'
SYNTH_MODULE = 'thor1v8ppstuf6e3x0r4glqc68d5jqcs2tf38cg2q6y'
BANK_MODULE = SYNTH_MODULE

LOAN_MARKER = '$+'

ZERO_HASH = '0000000000000000000000000000000000000000000000000000000000000000'

TREASURY_LP_ADDRESS = 'thor1egxvam70a86jafa8gcg3kqfmfax3s0m2g3m754'


class ThorRealms:
    RESERVES = 'Reserve'
    STANDBY_RESERVES = '.'

    BONDED = 'Bonded'
    BONDED_NODE = 'Bonded (node)'
    LIQ_POOL = 'Liquidity pools'
    RUNEPOOL = 'RUNEPool'
    POL = 'Protocol owned liquidity'
    CIRCULATING = 'Circulating'

    CEX = 'CEX'
    BURNED = 'Burned'
    MINTED = 'Minted'
    TREASURY = 'Treasury'
    MAYA_POOL = 'Maya liquidity pool'

    KILLED = 'Killed switched'
    INCOME_BURN = 'System income burn'


# todo: this information is already put in the config file
THOR_ADDRESS_DICT = {
    # Reserves:
    'thor1dheycdevq39qlkxs2a6wuuzyn4aqxhve4qxtxt': (ThorRealms.RESERVES, ThorRealms.RESERVES),
    'thor1lj62pg6ryxv2htekqx04nv7wd3g98qf9gfvamy': (ThorRealms.STANDBY_RESERVES, ThorRealms.STANDBY_RESERVES),

    # Treasury:
    'thor1qd4my7934h2sn5ag5eaqsde39va4ex2asz3yv5': ('Treasury Multisig', ThorRealms.TREASURY),  # empty now
    'thor10qh5272ktq4wes8ex343ky9rsuehcypddjh08k': ('Treasury Vultisig', ThorRealms.TREASURY),
    # 'thor1505gp5h48zd24uexrfgka70fg8ccedafsnj0e3': ('Treasury 1', ThorRealms.TREASURY),
    # 'thor14n2q7tpemxcha8zc26j0g5pksx4x3a9xw9ryq9': ('Treasury 2', ThorRealms.TREASURY),
    TREASURY_LP_ADDRESS: ('Treasury LP', ThorRealms.TREASURY),

    # CEX:
    "thor1t60f02r8jvzjrhtnjgfj4ne6rs5wjnejwmj7fh": ("Binance", ThorRealms.CEX),
    "thor1cqg8pyxnq03d88cl3xfn5wzjkguw5kh9enwte4": ("Binance", ThorRealms.CEX),
    "thor1uz4fpyd5f5d6p9pzk8lxyj4qxnwq6f9utg0e7k": ("Binance", ThorRealms.CEX),
    "thor1mtqtupwgjwn397w3dx9fqmqgzrfzq3240frash": ("Bybit", ThorRealms.CEX),
    "thor1ty6h2ll07fqfzumphp6kq3hm4ps28xlm2l6kd6": ("crypto.com", ThorRealms.CEX),
    "thor1jw0nhlmj4lv83dwhfknqnw6tmlvgw4xyf6rgd7": ("KuCoin", ThorRealms.CEX),
    "thor1hy2ka6xmqjfcwagtplyttayug4eqpqhu0sdu6r": ("KuCoin", ThorRealms.CEX),
    "thor15h7uv2339vdzt2a6qsjf6uh5zc06sed7szvze5": ("Ascendex", ThorRealms.CEX),
    "thor1nm0rrq86ucezaf8uj35pq9fpwr5r82clphp95t": ("Kraken", ThorRealms.CEX),
}

ADR17_TIMESTAMP = 1732626242  # Tuesday, 26 November 2024
