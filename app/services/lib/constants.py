from aiothornode.env import TEST_NET_ENVIRONMENT_MULTI_1, CHAOS_NET_BNB_ENVIRONMENT, MULTICHAIN_CHAOSNET_ENVIRONMENT
from aiothornode.types import ThorEnvironment

BNB_BNB_SYMBOL = 'BNB.BNB'
BNB_BUSD_SYMBOL = 'BNB.BUSD-BD1'
BNB_BUSD_TEST_SYMBOL = 'BNB.BUSD-BAF'
BNB_BUSD_TEST2_SYMBOL = 'BNB.BUSD-74E'

BNB_BTCB_SYMBOL = 'BNB.BTCB-1DE'
BNB_BTCB_TEST_SYMBOL = 'BNB.BTCB-101'
BTC_SYMBOL = 'BTC.BTC'

BCH_SYMBOL = 'BCH.BCH'

BNB_RUNE_SYMBOL = 'BNB.RUNE-B1A'
BNB_RUNE_TEST_SYMBOL = 'BNB.RUNE-67C'
NATIVE_RUNE_SYMBOL = 'THOR.RUNE'
RUNE_SYMBOL = NATIVE_RUNE_SYMBOL
RUNE_SYMBOL_DET = 'RUNE-DET'
RUNE_SYMBOL_MARKET = 'RUNE-MARKET'

BNB_ETHB_SYMBOL = 'BNB.ETH-1C9'
BNB_ETHB_TEST_SYMBOL = 'BNB.ETH-D5B'
ETH_RUNE_SYMBOL = 'ETH.THOR-0X3155BA85D5F96B2D030A4966AF206230E46849CB'
ETH_RUNE_SYMBOL_TEST = 'ETH.THOR-0XA0B515C058F127A15DD3326F490EBF47D215588E'
ETH_SYMBOL = 'ETH.ETH'

BNB_USDT_SYMBOL = 'BNB.USDT-6D8'
BNB_USDT_TEST_SYMBOL = 'BNB.USDT-DC8'
ETH_USDT_TEST_SYMBOL = 'ETH.USDT-0XA3910454BF2CB59B8B3A401589A3BACC5CA42306'
ETH_USDT_SYMBOL = 'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7'

STABLE_COIN_POOLS = (
    BNB_BUSD_SYMBOL, BNB_BUSD_TEST_SYMBOL, BNB_BUSD_TEST2_SYMBOL,
    BNB_USDT_SYMBOL, BNB_USDT_TEST_SYMBOL,
    ETH_USDT_TEST_SYMBOL, ETH_USDT_SYMBOL,
)

RUNE_SYMBOLS = (
    BNB_RUNE_SYMBOL,
    BNB_RUNE_TEST_SYMBOL,
    NATIVE_RUNE_SYMBOL,
)


def is_rune(symbol):
    return symbol in RUNE_SYMBOLS


def is_stable_coin(pool):
    return pool in STABLE_COIN_POOLS


class Chains:
    THOR = 'THOR'
    ETH = 'ETH'
    BTC = 'BTC'
    BCH = 'BCH'
    LTC = 'LTC'
    BNB = 'BNB'
    DOT = 'DOT'
    ZIL = 'ZIL'

    @staticmethod
    def detect_chain(address: str) -> str:
        address = address.lower()
        if address.startswith('0x'):
            return Chains.ETH
        elif address.startswith('thor') or address.startswith('tthor'):
            return Chains.THOR
        elif address.startswith('bnb') or address.startswith('tbnb'):
            return Chains.BNB
        return ''


class NetworkIdents:
    TESTNET_MULTICHAIN = 'testnet-multi'
    CHAOSNET_MULTICHAIN = 'chaosnet-multi'
    CHAOSNET_BEP2CHAIN = 'chaosnet-bep2'

    @classmethod
    def is_test(cls, network: str):
        return 'testnet' in network

    @classmethod
    def is_multi(cls, network: str):
        return 'multi' in network


THOR_DIVIDER = 100_000_000.0  # 1e8
THOR_DIVIDER_INV = 1.0 / THOR_DIVIDER

THOR_BLOCK_TIME = 6.0  # seconds. 10 blocks / minute


def get_thor_env_by_network_id(network_id) -> ThorEnvironment:
    if network_id == NetworkIdents.TESTNET_MULTICHAIN:
        return TEST_NET_ENVIRONMENT_MULTI_1.copy()
    elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return CHAOS_NET_BNB_ENVIRONMENT.copy()
    elif network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
        return MULTICHAIN_CHAOSNET_ENVIRONMENT.copy()
    else:
        # todo: add multi-chain chaosnet
        raise KeyError('unsupported network ID!')