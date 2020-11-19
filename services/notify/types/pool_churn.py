import logging
from copy import deepcopy
from typing import Dict

from localization import LocalizationManager, BaseLocalization
from services.fetch.base import INotified
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.models.pool_info import PoolInfo
from services.notify.broadcast import Broadcaster


class PoolChurnNotifier(INotified):
    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, loc_man: LocalizationManager):
        self.logger = logging.getLogger('CapFetcherNotification')
        self.broadcaster = broadcaster
        self.loc_man = loc_man
        self.cfg = cfg
        self.db = db
        self.old_pool_dict = {}

    async def on_data(self, sender: PoolPriceFetcher, fair_price):
        new_pool_dict = sender.price_holder.pool_info_map.copy()
        if not new_pool_dict:
            self.logger.warning('pool_info_map not filled yet..')
            return

        if self.old_pool_dict:
            # todo: persist old_pool_data in DB!
            # compare starting w 2nd iteration
            added_pools, removed_pools, changed_status_pools = self.compare_pool_sets(new_pool_dict)
            if added_pools or removed_pools or changed_status_pools:
                await self.broadcaster.notify_preconfigured_channels(self.loc_man,
                                                                     BaseLocalization.pool_churn_text,
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
