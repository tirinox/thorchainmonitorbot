import asyncio

from comm.picture.crypto_logo import CryptoLogoDownloader, check_pool_logos
from comm.picture.resources import Resources
from lib.config import SubConfig
from lib.cooldown import Cooldown
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.pool_info import PoolInfoMap, PoolChanges, PoolChange
from models.price import PriceHolder


LOGO_CHECK_TIMEOUT = 60.0  # sec; the check downloads, and the alert must not wait for a hanging download for long


class PoolChurnNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, logo_downloader: CryptoLogoDownloader = None):
        super().__init__()
        self.deps = deps
        self.logo_downloader = logo_downloader or CryptoLogoDownloader(Resources.LOGO_BASE)
        self.old_pool_dict = {}
        cfg: SubConfig = deps.cfg.pool_churn
        cooldown_sec = cfg.as_interval('notification.cooldown', '1h')
        self.spam_cd = Cooldown(self.deps.db, 'PoolChurnNotifier-spam', cooldown_sec)
        self.ignore_pool_removed = cfg.as_bool('notification.ignore_pool_removed', True)

    async def on_data(self, sender, data: PriceHolder):
        # compare starting w 2nd iteration
        if not self.old_pool_dict:
            self.old_pool_dict = data.pool_info_map
            return

        pool_changes = self.compare_pool_sets(data.pool_info_map)

        # self._dbg_pool_changes(pool_changes) # fixme: debug (!)

        if pool_changes.any_changed:
            await self.check_logos(pool_changes)
            pool_changes = pool_changes._replace(pool_info_map=data.pool_info_map, usd_per_rune=data.usd_per_rune)
            self.logger.info(f'Pool changes detected: added {pool_changes.pools_added}, '
                             f'removed {pool_changes.pools_removed}, changed {pool_changes.pools_changed}!')
            if await self.spam_cd.can_do():
                await self.pass_data_to_listeners(pool_changes)
                await self.spam_cd.do()

        self.old_pool_dict = data.pool_info_map

    async def check_logos(self, pool_changes: PoolChanges):
        """
        The card of a pool and the pictures of the bot need the logo of the asset and of its chain.
        A new or activated pool is checked as soon as it shows up, before the alert (which downloads what is missing),
        and the admin is told about a logo that is not there and cannot be downloaded.
        Never fails: it must not cost the alert.
        """
        names = list(dict.fromkeys(c.pool_name for c in (*pool_changes.pools_added, *pool_changes.activated)))
        if not names:
            return

        try:
            problems = await asyncio.wait_for(check_pool_logos(self.logo_downloader, names), LOGO_CHECK_TIMEOUT)
        except Exception as e:  # asyncio.TimeoutError too
            self.logger.exception(f'Failed to check the logos of {names}: {e!r}')
            problems = {'check': f'failed: {e!r}'}

        if problems:
            self.logger.error(f'No logos for {names}: {problems}')
            if emergency := getattr(self.deps, 'emergency', None):
                emergency.report(
                    'PoolChurnNotifier',
                    f'A new pool has no logo, and it cannot be downloaded: {", ".join(names)}. '
                    f'Put the picture into data/asset_logo, or the cards show a placeholder',
                    problems=problems)

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
