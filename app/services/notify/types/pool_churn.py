import logging
from typing import Dict

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.cooldown import Cooldown
from services.lib.date_utils import MINUTE, parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo, PoolInfoMap


class PoolChurnNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        self.old_pool_dict = {}
        cooldown_sec = parse_timespan_to_seconds(deps.cfg.pool_churn.notification.cooldown)
        self.spam_cd = Cooldown(self.deps.db, 'PoolChurnNotifier-spam', cooldown_sec)

    async def on_data(self, sender: PoolPriceFetcher, fair_price):
        new_pool_dict = self.deps.price_holder.pool_info_map.copy()
        if not new_pool_dict:
            self.logger.warning('pool_info_map not filled yet..')
            return

        if self.old_pool_dict:
            if not await self.spam_cd.can_do():
                self.logger.warning(f'Pool churn cooldown triggered:\n'
                                    f'{self.old_pool_dict = }\n'
                                    f'{new_pool_dict = }!')
                return

            # todo: persist old_pool_data in DB!
            # compare starting w 2nd iteration
            added_pools, removed_pools, changed_status_pools = self.compare_pool_sets(new_pool_dict)
            if added_pools or removed_pools or changed_status_pools:
                await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                          BaseLocalization.notification_text_pool_churn,
                                                                          added_pools,
                                                                          removed_pools,
                                                                          changed_status_pools)
                await self.spam_cd.do()

        self.old_pool_dict = new_pool_dict

    @staticmethod
    def split_pools_by_status(pim: PoolInfoMap):
        enabled_pools = set(p.asset for p in pim.values() if p.is_enabled)
        bootstrap_pools = set(pim.keys()) - enabled_pools
        return enabled_pools, bootstrap_pools

    def compare_pool_sets(self, new_pool_dict: PoolInfoMap):
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
