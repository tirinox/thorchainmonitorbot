import logging
from typing import Dict

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo


class PoolChurnNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger('CapFetcherNotification')
        self.old_pool_dict = {}

    async def on_data(self, sender: PoolPriceFetcher, fair_price):
        new_pool_dict = self.deps.price_holder.pool_info_map.copy()
        if not new_pool_dict:
            self.logger.warning('pool_info_map not filled yet..')
            return

        if self.old_pool_dict:
            # todo: persist old_pool_data in DB!
            # compare starting w 2nd iteration
            added_pools, removed_pools, changed_status_pools = self.compare_pool_sets(new_pool_dict)
            if added_pools or removed_pools or changed_status_pools:
                await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                          BaseLocalization.notification_text_pool_churn,
                                                                          added_pools,
                                                                          removed_pools,
                                                                          changed_status_pools)

        self.old_pool_dict = new_pool_dict

    @staticmethod
    def split_pools_by_status(pim: Dict[str, PoolInfo]):
        enabled_pools = set(p.asset for p in pim.values() if p.is_enabled)
        bootstrap_pools = set(pim.keys()) - enabled_pools
        return enabled_pools, bootstrap_pools

    def compare_pool_sets(self, new_pool_dict: Dict[str, PoolInfo]):
        new_pools = set(new_pool_dict.keys())
        old_pools = set(self.old_pool_dict.keys())
        all_pools = new_pools | old_pools

        changed_status_pools = []
        added_pools, removed_pools = [], []

        for name in all_pools:
            if name in new_pools and name in old_pools:
                old_status = self.old_pool_dict[name].status
                new_status = new_pool_dict[name].status
                if old_status != new_status:
                    changed_status_pools.append((name, old_status, new_status))
            elif name in new_pools and name not in old_pools:
                added_pools.append((name, new_pool_dict[name].status))
            elif name not in new_pools and name in old_pools:
                removed_pools.append((name, self.old_pool_dict[name].status))

        return added_pools, removed_pools, changed_status_pools
