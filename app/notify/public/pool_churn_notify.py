from jobs.fetch.pool_price import PoolInfoFetcherMidgard
from lib.config import SubConfig
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.pool_info import PoolInfoMap, PoolChanges, PoolChange


class PoolChurnNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.old_pool_dict = {}
        cfg: SubConfig = deps.cfg.pool_churn
        cooldown_sec = cfg.as_interval('notification.cooldown', '1h')
        self.spam_cd = Cooldown(self.deps.db, 'PoolChurnNotifier-spam', cooldown_sec)
        self.ignore_pool_removed = cfg.as_bool('notification.ignore_pool_removed', True)

    async def on_data(self, sender: PoolInfoFetcherMidgard, data: PoolInfoMap):
        # compare starting w 2nd iteration
        if not self.old_pool_dict:
            self.old_pool_dict = data
            return

        pool_changes = self.compare_pool_sets(data)

        # self._dbg_pool_changes(pool_changes) # fixme: debug (!)

        if pool_changes.any_changed:
            self.logger.info(f'Pool changes detected: {pool_changes}!')
            if await self.spam_cd.can_do():
                await self.pass_data_to_listeners(pool_changes)
                await self.spam_cd.do()

        self.old_pool_dict = data

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
                if not self.ignore_pool_removed:
                    status = self.old_pool_dict[name].status
                    removed_pools.append(PoolChange(name, status, status))

        return PoolChanges(added_pools, removed_pools, changed_status_pools)

    @staticmethod
    def _dbg_pool_changes(pool_changes):
        import random
        def rnd_status():
            return random.choice(['staged', 'available', 'Staged', 'Available', 'STAGED', 'AVAILABLE'])

        pool_changes.pools_added.append(PoolChange('BNB.LOL-123', rnd_status(), rnd_status()))
        pool_changes.pools_removed.append(PoolChange('BNB.LOL-123', rnd_status(), rnd_status()))
        pool_changes.pools_changed.append(PoolChange('BNB.LOL-123', rnd_status(), rnd_status()))
        return pool_changes
