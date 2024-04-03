import json
from contextlib import suppress

from services.lib.cooldown import Cooldown
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.loans import LendingStats, AlertLendingStats


class LendingStatsNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        notify_cd_sec = deps.cfg.as_interval('borrowers.cooldown', '2d')
        self.cd = Cooldown(self.deps.db, 'LendingStats', notify_cd_sec)

    async def on_data(self, sender, event: LendingStats):
        if await self.cd.can_do():
            prev_data = await self._load_old_stats()
            new_event = AlertLendingStats(event, prev_data)
            await self.pass_data_to_listeners(new_event)
            await self.cd.do()

            await self._save_old_stats(event)

    KEY_DB_LENDING_STATS = 'Lending:LastStats'

    async def _save_old_stats(self, stats: LendingStats):
        j = json.dumps((stats._asdict()))
        await self.deps.db.redis.set(self.KEY_DB_LENDING_STATS, j)

    async def _load_old_stats(self):
        try:
            j = await self.deps.db.redis.get(self.KEY_DB_LENDING_STATS)
            j = json.loads(j)
            return LendingStats(**j)
        except Exception as e:
            self.logger.exception(e)
            return None
