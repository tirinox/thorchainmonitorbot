from contextlib import suppress
from typing import List

from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.tx import ThorTx


class VolumeFillerUpdater(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.update_pools_each_time = True

    async def on_data(self, sender, txs: List[ThorTx]):
        try:
            # update & fill
            await self.fill_volumes(txs)
        except Exception as e:
            self.logger.exception(f"Fill volume failed: {e}", exc_info=e)

        # send to the listeners
        await self.pass_data_to_listeners(txs, sender=(sender, self))  # pass it to the next subscribers

    async def fill_volumes(self, txs: List[ThorTx]):
        if not txs:
            return

        ppf: PoolFetcher = self.deps.pool_fetcher

        if self.update_pools_each_time:
            # we need here most relevant pool state to estimate % of pool after TX
            pool_info_map = await ppf.reload_global_pools()
        else:
            pool_info_map = self.deps.price_holder.pool_info_map
            if not pool_info_map:
                pool_info_map = await ppf.reload_global_pools()

        for tx in txs:
            tx.calc_full_rune_amount(pool_info_map)
