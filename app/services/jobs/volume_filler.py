from typing import List

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfo
from services.models.tx import ThorTxExtended, ThorTx


class VolumeFillerUpdater(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, extended_txs: List[ThorTxExtended]):
        # update & fill
        await self._fill_volumes(extended_txs)
        # send to the listeners
        await self.pass_data_to_listeners(extended_txs, sender=(sender, self))  # pass it to the next subscribers

    async def _fill_volumes(self, txs: List[ThorTxExtended]):
        if not txs:
            return

        ppf: PoolPriceFetcher = self.deps.price_pool_fetcher
        # we need here most relevant pool state to estimate % of pool after TX
        pool_info_map = await ppf.reload_global_pools()

        for tx in txs:
            pool_info: PoolInfo = pool_info_map.get(tx.first_pool)

            asset_per_rune = pool_info.asset_per_rune if pool_info else 0.0
            tx.calc_full_rune_amount(asset_per_rune)
