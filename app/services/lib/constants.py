from typing import NamedTuple

from services.lib.date_utils import MINUTE

BNB_BNB_SYMBOL = 'BNB.BNB'

BNB_BUSD_SYMBOL = 'BNB.BUSD-BD1'
BNB_BUSD_TEST_SYMBOL = 'BNB.BUSD-BAF'
BNB_BUSD_TEST2_SYMBOL = 'BNB.BUSD-74E'

BNB_BTCB_SYMBOL = 'BNB.BTCB-1DE'
BNB_BTCB_TEST_SYMBOL = 'BNB.BTCB-101'
BTC_SYMBOL = 'BTC.BTC'

BCH_SYMBOL = 'BCH.BCH'

BNB_RUNE_SYMBOL_NO_CHAIN = 'RUNE-B1A'
BNB_RUNE_SYMBOL = 'BNB.RUNE-B1A'

BNB_RUNE_TEST_SYMBOL = 'BNB.RUNE-67C'
ETH_RUNE_SYMBOL = 'ETH.RUNE-0X3155BA85D5F96B2D030A4966AF206230E46849CB'
ETH_RUNE_SYMBOL_TEST = 'ETH.RUNE-0XA0B515C058F127A15DD3326F490EBF47D215588E'
NATIVE_RUNE_SYMBOL = 'THOR.RUNE'
RUNE_SYMBOL = NATIVE_RUNE_SYMBOL

RUNE_SYMBOL_DET = 'RUNE-DET'
RUNE_SYMBOL_POOL = 'RUNE-MARKET'
RUNE_SYMBOL_CEX = 'RUNE-MARKET-CEX'

BNB_ETHB_SYMBOL = 'BNB.ETH-1C9'
BNB_ETHB_TEST_SYMBOL = 'BNB.ETH-D5B'
ETH_SYMBOL = 'ETH.ETH'
AVAX_SYMBOL = 'AVAX.AVAX'

BNB_USDT_SYMBOL = 'BNB.USDT-6D8'
BNB_USDT_TEST_SYMBOL = 'BNB.USDT-DC8'
ETH_USDT_TEST_SYMBOL = 'ETH.USDT-0XA3910454BF2CB59B8B3A401589A3BACC5CA42306'
ETH_USDT_SYMBOL = 'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7'

ETH_USDC_SYMBOL = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'

DOGE_SYMBOL = 'DOGE.DOGE'

UST_SYMBOL = 'TERRA.USD'

RUNE_IDEAL_SUPPLY = 500_000_000

STABLE_COIN_POOLS_ALL = (
    BNB_BUSD_SYMBOL, BNB_BUSD_TEST_SYMBOL, BNB_BUSD_TEST2_SYMBOL,
    BNB_USDT_SYMBOL, BNB_USDT_TEST_SYMBOL,
    ETH_USDT_TEST_SYMBOL, ETH_USDT_SYMBOL,
    ETH_USDC_SYMBOL, UST_SYMBOL
)

STABLE_COIN_BNB_POOLS = (
    BNB_BUSD_SYMBOL, BNB_BUSD_TEST_SYMBOL, BNB_BUSD_TEST2_SYMBOL,
)

STABLE_COIN_POOLS = STABLE_COIN_BNB_POOLS
# STABLE_COIN_POOLS = STABLE_COIN_BNB_POOLS

RUNE_SYMBOLS = (
    BNB_RUNE_SYMBOL,
    BNB_RUNE_TEST_SYMBOL,
    ETH_RUNE_SYMBOL,
    ETH_RUNE_SYMBOL_TEST,
    NATIVE_RUNE_SYMBOL,
)

DEFAULT_CEX_NAME = 'HitBTC'
DEFAULT_CEX_BASE_ASSET = 'USDT'


def is_rune(symbol):
    return symbol == NATIVE_RUNE_SYMBOL


def rune_origin(symbol):
    if symbol in (ETH_RUNE_SYMBOL, ETH_RUNE_SYMBOL_TEST):
        return 'ERC20'
    elif symbol in (BNB_RUNE_SYMBOL, BNB_RUNE_TEST_SYMBOL):
        return 'BEP2'
    elif symbol == NATIVE_RUNE_SYMBOL:
        return 'Native'
    else:
        return 'Unknown'


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
    TERRA = 'TERRA'  # bye-bye
    AVAX = 'AVAX'
    ATOM = 'GAIA'

    META_ALL = (THOR, ETH, BTC, BCH, LTC, BNB, DOGE, AVAX, ATOM)

    @staticmethod
    def detect_chain(orig_address: str) -> str:
        address = orig_address.lower()
        if address.startswith('0x'):
            return Chains.ETH  # or other EVM chain??
        elif address.startswith('terra'):
            return Chains.TERRA
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
        elif chain == Chains.TERRA:
            return 6.64
        elif chain == Chains.ATOM:
            return 6.85
        elif chain == Chains.AVAX:
            return 3.0
        return 0.01

    @staticmethod
    def web3_chain_id(chain: str) -> int:
        if chain == Chains.ETH:
            return 0x1
        elif chain == Chains.AVAX:
            return 43114

    @staticmethod
    def l1_asset(chain: str) -> str:
        assert chain in Chains.META_ALL
        return f'{chain}.{chain}'


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


THOR_DIVIDER = 100_000_000.0  # 1e8
THOR_DIVIDER_INV = 1.0 / THOR_DIVIDER

THOR_BLOCK_TIME = 6.0  # seconds. 10 blocks / minute
THOR_BLOCK_SPEED = 1 / THOR_BLOCK_TIME
THOR_BLOCKS_PER_MINUTE = MINUTE * THOR_BLOCK_SPEED

THOR_BASIS_POINT_MAX = 10_000


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
