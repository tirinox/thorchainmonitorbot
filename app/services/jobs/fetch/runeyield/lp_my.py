import asyncio
from typing import List, Tuple, Dict

from aiothornode.types import ThorPool

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase
from services.jobs.fetch.tx import TxFetcher
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import MidgardURLGenBase
from services.lib.depcont import DepContainer
from services.models.pool_member import PoolMemberDetails
from services.models.stake_info import StakePoolReport, CurrentLiquidity
from services.models.tx import ThorTx


class HomebrewLPConnector(AsgardConsumerConnectorBase):
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        super().__init__(deps, ppf, url_gen)
        self.tx_fetcher = TxFetcher(deps)
        self.parser = get_parser_by_network_id(deps.cfg.network_id)
        self.use_thor_consensus = True

    async def generate_yield_summary(self, address, pools: List[str]) -> Tuple[dict, List[StakePoolReport]]:
        pass

    async def generate_yield_report_single_pool(self, address, pool) -> StakePoolReport:
        # todo: idea check date_last_added, if it is not changed - get user_txs from local cache
        user_txs = await self._get_user_tx_actions(address, pool)

        historic_pool_states, current_pools_details = await asyncio.gather(
            self._fetch_historical_pool_states(user_txs),
            self._get_details_of_staked_pools(address, pool)
        )

        # filter only 1 pool
        historic_pool_states = {height: pools[pool] for height, pools in historic_pool_states.items()}
        current_pool_details: PoolMemberDetails = current_pools_details.get(pool)

        print('--- POOLS ---')

        for height, pool_info in historic_pool_states.items():
            print(height)
            print(pool_info)
            print('-----')

        print()
        print('--- TXS ---')

        for tx in user_txs:
            print(tx)
            print(historic_pool_states[tx.height_int])
            print('-----')

        print()
        print('--- CURRENT POOL INFO ---')

        print(current_pool_details)

        # return StakePoolReport()  # todo

    async def get_my_pools(self, address) -> List[str]:
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return self.parser.parse_pool_membership(j)

    # ----

    async def _get_user_tx_actions(self, address: str, pool_filter=None) -> List[ThorTx]:
        txs = await self.tx_fetcher.fetch_user_tx(address, liquidity_change_only=True)
        if pool_filter:
            txs = [tx for tx in txs if pool_filter in tx.pools]
        return txs

    async def _fetch_historical_pool_states(self, txs: List[ThorTx]) -> Dict[int, Dict[str, ThorPool]]:
        heights = list(set(tx.height_int for tx in txs))
        thor_conn = self.deps.thor_connector

        # make sure, that connections are fresh, in order not to update it at all the height simultaneously
        await thor_conn._get_random_clients()

        tasks = [
            thor_conn.query_pools(h, consensus=self.use_thor_consensus) for h in heights
        ]
        pool_states = await asyncio.gather(*tasks)
        pool_states = [{p.asset: p for p in pools} for pools in pool_states]
        return dict(zip(heights, pool_states))

    async def _get_details_of_staked_pools(self, address, pools) -> Dict[str, PoolMemberDetails]:
        url = self.url_gen.url_details_of_pools(address, pools)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            if 'error' in j:
                raise FileNotFoundError(j['error'])
            pool_array = self.parser.parse_pool_member_details(j, address)
            return {p.pool: p for p in pool_array}

    async def _get_current_liquidity(self, txs: List[ThorTx], pool_details: PoolMemberDetails) -> CurrentLiquidity:
        ...