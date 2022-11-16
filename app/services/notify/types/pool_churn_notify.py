from localization.manager import BaseLocalization
from services.jobs.fetch.pool_price import PoolInfoFetcherMidgard
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfoMap, PoolChanges, PoolChange
from services.models.price import RuneMarketInfo


class PoolChurnNotifier(INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.old_pool_dict = {}
        cooldown_sec = parse_timespan_to_seconds(deps.cfg.pool_churn.notification.cooldown)
        self.spam_cd = Cooldown(self.deps.db, 'PoolChurnNotifier-spam', cooldown_sec)

    async def on_data(self, sender: PoolInfoFetcherMidgard, data: RuneMarketInfo):
        # compare starting w 2nd iteration
        if not self.old_pool_dict:
            self.old_pool_dict = data.pools
            return

        pool_changes = self.compare_pool_sets(data.pools)

        if pool_changes.any_changed:
            self.logger.info(f'Pool changes detected: {pool_changes}!')
            if await self.spam_cd.can_do():
                await self.deps.broadcaster.notify_preconfigured_channels(
                    BaseLocalization.notification_text_pool_churn,
                    pool_changes)
                await self.spam_cd.do()

        self.old_pool_dict = data.pools

    @staticmethod
    def split_pools_by_status(pim: PoolInfoMap):
        enabled_pools = set(p.asset for p in pim.values() if p.is_enabled)
        bootstrap_pools = set(pim.keys()) - enabled_pools
        return enabled_pools, bootstrap_pools

    def compare_pool_sets(self, new_pool_dict: PoolInfoMap) -> PoolChanges:
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
                    changed_status_pools.append(PoolChange(name, old_status, new_status))
            elif name in new_pools and name not in old_pools:
                status = new_pool_dict[name].status
                added_pools.append(PoolChange(name, status, status))
            elif name not in new_pools and name in old_pools:
                status = self.old_pool_dict[name].status
                removed_pools.append(PoolChange(name, status, status))

        return PoolChanges(added_pools, removed_pools, changed_status_pools)

    @staticmethod
    def _dbg_pool_changes(pool_changes):
        pool_changes.pools_added.append(PoolChange('BNB.LOL-123', 'staged', 'staged'))
        pool_changes.pools_removed.append(PoolChange('BNB.LOL-123', 'staged', 'staged'))
        pool_changes.pools_changed.append(PoolChange('BNB.LOL-123', 'staged', 'available'))
        return pool_changes
