from abc import ABC, abstractmethod

from aiothornode.env import TEST_NET_ENVIRONMENT_MULTI_1, CHAOS_NET_BNB_ENVIRONMENT, MULTICHAIN_CHAOSNET_ENVIRONMENT

from services.lib.constants import NetworkIdents


class MidgardURLGenBase(ABC):
    LIQUIDITY_TX_TYPES_STRING = ''

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    @abstractmethod
    def url_for_tx(self, offset=0, count=50, address=None, types=None) -> str:
        ...

    @abstractmethod
    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        ...

    @abstractmethod
    def url_for_address_pool_membership(self, address) -> str:
        ...

    @abstractmethod
    def url_details_of_pools(self, address, pools) -> str:
        ...

    @abstractmethod
    def url_mimir(self):
        ...

    @abstractmethod
    def url_network(self):
        ...

    @abstractmethod
    def url_last_block(self):
        ...

    @abstractmethod
    def url_stats(self):
        ...

    @abstractmethod
    def url_thor_nodes(self):
        ...


class MidgardURLGenV1(MidgardURLGenBase):
    LIQUIDITY_TX_TYPES_STRING = 'stake,unstake'

    def url_for_tx(self, offset=0, count=50, address=None, types=None) -> str:
        url = f'{self.base_url}/v1/txs?offset={offset}&limit={count}'
        if address:
            url += f'&address={address}'
        if types:
            url += f'&type={types}'
        return url

    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        return f"{self.base_url}/v1/history/pools?pool={pool}&interval=day&from={from_ts}&to={to_ts}"

    def url_for_address_pool_membership(self, address) -> str:
        return f"{self.base_url}/v1/stakers/{address}"

    def url_details_of_pools(self, address, pools) -> str:
        pools = pools if isinstance(pools, str) else ','.join(pools)
        return f'{self.base_url}/v1/stakers/{address}/pools?asset={pools}'

    def url_mimir(self):
        return f'{self.base_url}/v1/thorchain/mimir'

    def url_network(self):
        return f'{self.base_url}/v1/network'

    def url_last_block(self):
        return f'{self.base_url}/v1/thorchain/lastblock'

    def url_stats(self):
        return f'{self.base_url}/v1/stats'

    def url_thor_nodes(self):
        return f'{self.base_url}/v1/thorchain/nodes'  # todo: is it correct?


class MidgardURLGenV2(MidgardURLGenBase):
    LIQUIDITY_TX_TYPES_STRING = 'withdraw,addLiquidity'

    def url_for_tx(self, offset=0, count=50, address=None, types=None) -> str:
        url = f'{self.base_url}/v2/actions?offset={offset}&limit={count}'
        if address:
            url += f'&address={address}'
        if types:
            url += f'&type={types}'
        return url

    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        return f"{self.base_url}/v2/history/depths/{pool}?interval=day&from={from_ts}&to={to_ts}"

    def url_for_address_pool_membership(self, address) -> str:
        return f"{self.base_url}/v2/member/{address}"

    def url_details_of_pools(self, address, pools) -> str:
        return f'{self.base_url}/v2/member/{address}'  # no need pools

    def url_mimir(self):
        return f'{self.base_url}/v2/thorchain/mimir'

    def url_network(self):
        return f'{self.base_url}/v2/network'

    def url_last_block(self):
        return f'{self.base_url}/v2/thorchain/lastblock'

    def url_stats(self):
        return f'{self.base_url}/v2/stats'

    def url_thor_nodes(self):
        return f'{self.base_url}/v2/thorchain/nodes'


def get_url_gen_by_network_id(network_id) -> MidgardURLGenBase:
    if network_id == NetworkIdents.TESTNET_MULTICHAIN:
        return MidgardURLGenV2(TEST_NET_ENVIRONMENT_MULTI_1.midgard_url)
    elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return MidgardURLGenV1(CHAOS_NET_BNB_ENVIRONMENT.midgard_url)
    elif network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
        return MidgardURLGenV2(MULTICHAIN_CHAOSNET_ENVIRONMENT.midgard_url)
    else:
        raise KeyError('unsupported network ID!')
