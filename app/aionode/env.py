from copy import copy
from dataclasses import dataclass


@dataclass
class ThorEnvironment:
    seed_url: str = ''
    midgard_url: str = ''
    thornode_url: str = ''
    rpc_url: str = ''

    timeout: float = 6.0

    retries: int = 1
    retry_delay: float = 0.0

    path_queue: str = '/thorchain/queue'
    path_nodes: str = '/thorchain/nodes'
    path_pools: str = "/thorchain/pools"
    path_pools_height: str = "/thorchain/pools?height={height}"
    path_pool: str = "/thorchain/pool/{pool}"
    path_pool_height: str = "/thorchain/pool/{pool}?height={height}"

    path_last_blocks: str = "/thorchain/lastblock"
    path_constants: str = "/thorchain/constants"
    path_mimir: str = "/thorchain/mimir"
    path_mimir_nodes: str = '/thorchain/mimir/nodes'
    path_mimir_votes: str = '/thorchain/mimir/nodes_all'
    path_inbound_addresses: str = "/thorchain/inbound_addresses"
    path_vault_yggdrasil: str = "/thorchain/vaults/yggdrasil"
    path_vault_asgard: str = "/thorchain/vaults/asgard"
    path_balance: str = '/cosmos/bank/v1beta1/balances/{address}'
    path_block_by_height: str = '/block?height={height}'
    path_tx_by_hash: str = '/cosmos/tx/v1beta1/txs/{hash}'
    path_tx_by_hash_old: str = '/tx?hash={hash}'
    path_tx_search: str = '/tx_search?query={query}&prove={prove}&page={page}&per_page={per_page}&order_by={order_by}'

    path_genesis: str = '/genesis'
    path_status: str = '/status?'

    path_liq_provider_details = '/thorchain/pool/{asset}/liquidity_provider/{address}?height={height}'
    path_liq_providers = '/thorchain/pool/{asset}/liquidity_providers?height={height}'

    path_saver_details = '/thorchain/pool/{asset}/saver/{address}?height={height}'
    path_savers = '/thorchain/pool/{asset}/savers?height={height}'
    path_pol = '/thorchain/pol?height={height}'
    path_network = '/thorchain/network?height={height}'

    path_block_results = '/block_results?height={height}'

    kind: str = ''

    def copy(self):
        return copy(self)

    def set_timeout(self, timeout):
        assert timeout > 0.0
        self.timeout = timeout
        return self

    def set_retries(self, retries=1, delay=0.0):
        assert retries >= 1
        self.retries = retries
        self.retry_delay = delay
        return self


class ThorURL:
    class THORNode:
        PUBLIC = 'https://thornode.thorchain.info'
        NINE_REALMS = 'https://thornode.ninerealms.com'
        THORSWAP = 'https://thornode.thorswap.net'

        STAGENET = 'https://stagenet-thornode.ninerealms.com'
        TESTNET = 'https://testnet.thornode.thorchain.info'

    class RPC:
        PUBLIC = 'https://rpc.thorchain.info'
        NINE_REALMS = 'https://rpc.ninerealms.com'
        THORSWAP = 'https://rpc.thorswap.net'

        STAGENET = 'https://stagenet-rpc.ninerealms.com'
        TESTNET = 'https://testnet.rpc.thorchain.info/'

    class Midgard:
        PUBLIC = 'https://midgard.thorchain.info'
        NINE_REALMS = 'https://midgard.ninerealms.com'
        THORSWAP = 'https://midgard.thorswap.net'

        STAGENET = 'https://stagenet-midgard.ninerealms.com'
        TESTNET = 'https://testnet.midgard.thorchain.info'

    class Seed:
        MAINNET = 'https://seed.thorchain.info'
        TESTNET = 'https://testnet.seed.thorchain.info'


TEST_NET_ENVIRONMENT_MULTI_1 = ThorEnvironment(
    seed_url=ThorURL.Seed.TESTNET,
    midgard_url=ThorURL.Midgard.TESTNET,
    thornode_url=ThorURL.THORNode.TESTNET,
    rpc_url=ThorURL.RPC.TESTNET,
    kind='testnet',
)

MULTICHAIN_STAGENET_ENVIRONMENT = ThorEnvironment(
    midgard_url=ThorURL.Midgard.STAGENET,
    thornode_url=ThorURL.THORNode.STAGENET,
    rpc_url=ThorURL.RPC.STAGENET,
    kind='stagenet',
)

MAINNET_ENVIRONMENT = ThorEnvironment(
    seed_url=ThorURL.Seed.MAINNET,
    midgard_url=ThorURL.Midgard.NINE_REALMS,
    thornode_url=ThorURL.THORNode.NINE_REALMS,
    rpc_url=ThorURL.RPC.NINE_REALMS,
    kind='mainnet',
)

MULTICHAIN_MAINNET_9R_ENVIRONMENT = ThorEnvironment(
    seed_url=ThorURL.Seed.MAINNET,
    midgard_url=ThorURL.Midgard.NINE_REALMS,
    thornode_url=ThorURL.THORNode.NINE_REALMS,
    rpc_url=ThorURL.RPC.NINE_REALMS,
    kind='mainnet',
)

MULTICHAIN_MAINNET_THORSWAP_ENVIRONMENT = ThorEnvironment(
    seed_url=ThorURL.Seed.MAINNET,
    midgard_url=ThorURL.Midgard.THORSWAP,
    thornode_url=ThorURL.THORNode.THORSWAP,
    rpc_url=ThorURL.RPC.THORSWAP,
    kind='mainnet',
)

MAINNET = MAINNET_ENVIRONMENT  # alias
STAGENET = MULTICHAIN_STAGENET_ENVIRONMENT  # alias
MCTN = TEST_NET_ENVIRONMENT_MULTI_1  # alias
MCCN_9R = MULTICHAIN_MAINNET_9R_ENVIRONMENT  # alias
MCCN_THORSWAP = MULTICHAIN_MAINNET_THORSWAP_ENVIRONMENT  # alias

THORNODE_PORT = 1317
TENDERMINT_RPC_PORT_TESTNET = 26657
TENDERMINT_RPC_PORT_MAINNET = 27147
