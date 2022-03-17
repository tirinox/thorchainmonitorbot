from abc import ABC, abstractmethod

from services.lib.utils import iterable_but_not_str


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

    @abstractmethod
    def url_pool_info(self):
        ...


class MidgardURLGenV2(MidgardURLGenBase):
    LIQUIDITY_TX_TYPES_STRING = 'withdraw,addLiquidity'

    def url_for_tx(self, offset=0, count=50, address=None, types=None, txid=None) -> str:
        url = f'{self.base_url}/v2/actions?offset={offset}&limit={count}'
        if address:
            url += f'&address={address}'
        if types:
            if iterable_but_not_str(types):
                types = ','.join(types)
            url += f'&type={types}'
        if txid:
            url += f'&txid={txid}'

        return url

    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        return f"{self.base_url}/v2/history/depths/{pool}?interval=day&from={from_ts}&to={to_ts}"

    def url_for_swap_history(self, from_ts=0, to_ts=0, days=10) -> str:
        if not from_ts and not to_ts:
            spec = f'from={from_ts}&to={to_ts}'
        else:
            spec = f'counts={days}'
        return f"{self.base_url}/v2/history/swaps?interval=day&{spec}"

    def url_for_address_pool_membership(self, address) -> str:
        return f"{self.base_url}/v2/member/{address}"

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

    def url_pool_info(self):
        return f'{self.base_url}/v2/pools'


free_url_gen = MidgardURLGenV2('')
