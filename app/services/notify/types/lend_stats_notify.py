import json
from contextlib import suppress
from typing import Optional

from services.lib.cooldown import Cooldown
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.loans import LendingStats, AlertLendingStats, PoolLendState


class LendingStatsNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        notify_cd_sec = deps.cfg.as_interval('borrowers.cooldown', '2d')
        self.cd = Cooldown(self.deps.db, 'LendingStats', notify_cd_sec)

    async def on_data(self, sender, event: LendingStats):
        if await self.cd.can_do():
            prev_data = await self._load_old_stats(is_latest=False)
            new_event = AlertLendingStats(event, prev_data)
            await self.pass_data_to_listeners(new_event)
            await self.cd.do()

            await self._save_old_stats(event, is_latest=False)
        await self._save_old_stats(event, is_latest=True)

    KEY_DB_LENDING_STATS_PREV = 'Lending:LastStats:Previous'  # since the last posted update
    KEY_DB_LENDING_STATS_LATEST = 'Lending:LastStats:Latest'  # stored every tick

    def _db_key(self, is_latest):
        return self.KEY_DB_LENDING_STATS_LATEST if is_latest else self.KEY_DB_LENDING_STATS_PREV

    async def _save_old_stats(self, stats: LendingStats, is_latest):
        j = json.dumps((stats._asdict()))
        await self.deps.db.redis.set(self._db_key(is_latest), j)

    async def _load_old_stats(self, is_latest):
        try:
            j = await self.deps.db.redis.get(self._db_key(is_latest))
            j = json.loads(j)
            stats = LendingStats(**j)
            stats = stats._replace(pools=[
                PoolLendState(*p) for p in stats.pools
            ])
            return stats
        except Exception as e:
            self.logger.exception(e)
            return None

    async def get_last_event(self) -> Optional[AlertLendingStats]:
        prev_data = await self._load_old_stats(is_latest=True)
        return AlertLendingStats(prev_data, None) if prev_data else None
