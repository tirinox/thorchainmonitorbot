from jobs.ruji_merge import RujiMergeTracker
from lib.cooldown import Cooldown
from lib.date_utils import now_ts, DAY
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.ruji import AlertRujiraMergeStats


class RujiMergeStatsTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.cd_sec = deps.cfg.as_interval("rujira.merge.period", "1d")
        self.spam_cd = Cooldown(self.deps.db, 'Rujira:MergeStats', self.cd_sec)
        self.ruji_merge_tracker = RujiMergeTracker(deps)

        self.stats_days_back = round(self.cd_sec / DAY)

    async def on_data(self, sender, merge_stats):
        if await self.spam_cd.can_do():
            top_txs = await self.ruji_merge_tracker.get_top_events_from_db(now_ts(), self.stats_days_back)
            self.logger.info(f"Days back {self.stats_days_back} -> {len(top_txs)} merge txs")
            alert = AlertRujiraMergeStats(merge_stats, top_txs, self.stats_days_back)
            await self.pass_data_to_listeners(alert)
            await self.spam_cd.do()
