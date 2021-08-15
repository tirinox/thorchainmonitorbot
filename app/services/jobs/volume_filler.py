from typing import List

from services.jobs.fetch.base import INotified, WithDelegates
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.pool_info import PoolInfo
from services.models.tx import ThorTxExtended, ThorTx


class VolumeFillerUpdater(WithDelegates, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.logger = class_logger(self)

    async def on_data(self, sender, txs: List[ThorTx]):
        # transform
        extended_txs = [ThorTxExtended.load_from_thor_tx(tx) for tx in txs]
        # update & fill
        await self._fill_volumes(extended_txs)
        # send to the listeners
        await self.handle_data(extended_txs, sender=(sender, self))  # pass it to the next subscribers

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
