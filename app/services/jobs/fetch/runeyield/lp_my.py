import asyncio
from typing import List, Tuple, Dict

from aiothornode.types import ThorPool

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase
from services.jobs.fetch.tx import TxFetcher
from services.lib.midgard.urlgen import MidgardURLGenBase
from services.lib.depcont import DepContainer
from services.models.stake_info import StakePoolReport
from services.models.tx import ThorTx


class HomebrewLPConnector(AsgardConsumerConnectorBase):
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        super().__init__(deps, ppf, url_gen)
        self.tx_fetcher = TxFetcher(deps)
        self.use_thor_consensus = True

    async def generate_yield_summary(self, address, pools: List[str]) -> Tuple[dict, List[StakePoolReport]]:
        pass

    async def generate_yield_report_single_pool(self, address, pool) -> StakePoolReport:
        user_txs = await self._get_user_tx_actions(address, pool)

        historic_pool_states = await self._fetch_historical_pool_states(user_txs)

        print('--- POOLS ---')

        for height, pools in historic_pool_states.items():
            print('-----')
            print(height)
            pool_info = pools.get(pool)
            print(pool_info)

        print('--- TXS ---')

        for tx in user_txs:
            print(tx)
            print(historic_pool_states[tx.height_int].get(pool))

        # return StakePoolReport()  # todo

    async def get_my_pools(self, address) -> List[str]:
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            if 'pools' in j:  # v2
                pools = j['pools']
                return [p['pool'] for p in pools]
            else:
                my_pools = j['poolsArray']
                return my_pools

    # ----

    async def _get_user_tx_actions(self, address: str, pool_filter=None):
        txs = await self.tx_fetcher.fetch_user_tx(address, liquidity_change_only=True)
        if pool_filter:
            txs = [tx for tx in txs if pool_filter in tx.pools]
        return txs

    async def _fetch_historical_pool_states(self, txs: List[ThorTx]) -> Dict[int, Dict[str, ThorPool]]:
        heights = list(set(tx.height_int for tx in txs))
        thor_conn = self.deps.thor_connector

        # make sure, that connections are fresh, in order not to update it at all the height simulteneously
        await thor_conn._get_random_clients()

        tasks = [
            thor_conn.query_pools(h, consensus=self.use_thor_consensus) for h in heights
        ]
        pool_states = await asyncio.gather(*tasks)
        pool_states = [{p.asset: p for p in pools} for pools in pool_states]
        return dict(zip(heights, pool_states))

    async def _get_details_of_staked_pools(self):
        ...


"""

Midgard V1

https://chaosnet-midgard.bepswap.com/v1/stakers/bnb1lc66rzzudra4e0qrw4qemgupd0f0ctd5m03svx/pools?asset=BNB.ADA-9F4

asset=BNB.ADA-9F4,BNB.BNB  - can pass comma-separated list

[{"asset":"BNB.ADA-9F4","assetStaked":"65468181153","assetWithdrawn":"0","dateFirstStaked":1613318061,"heightLastStaked":2733834,"runeStaked":"13834714223","runeWithdrawn":"0","units":"18274712848"}]

units = final units after all add/withdraw


Midgard V2

https://testnet.midgard.thorchain.info/v2/member/tthor1qkd5f9xh2g87wmjc620uf5w08ygdx4etu0u9fs

{
	"pools": [
		{
			"assetAdded": "500000000",
			"assetAddress": "qz7pmntvnlujmtpz9n5j5yc5m0tta0k3hy4nk5eg8g",
			"assetWithdrawn": "0",
			"dateFirstAdded": "1617701865",
			"dateLastAdded": "1617701865",
			"liquidityUnits": "33800000000",
			"pool": "BCH.BCH",
			"runeAdded": "33800000000",
			"runeAddress": "tthor1qkd5f9xh2g87wmjc620uf5w08ygdx4etu0u9fs",
			"runeWithdrawn": "0"
		},
		{
		....
		}
]

"""
