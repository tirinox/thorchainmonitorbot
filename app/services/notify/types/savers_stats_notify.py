from typing import Optional

from services.jobs.fetch.savers_vnx import SaversStatsFetcher
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import short_dollar
from services.lib.utils import WithLogger


class SaversStatsNotifier(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer, ssf: Optional[SaversStatsFetcher]):
        super().__init__()
        self.deps = deps

        cd_notify = deps.cfg.as_interval('saver_stats.period', '7d')
        self.cd_notify = Cooldown(deps.db, 'SaverStats:Notify', cd_notify)

        self.data_source = ssf or SaversStatsFetcher(deps)

    async def on_data(self, sender, _):
        if await self.cd_notify.can_do():
            await self.cd_notify.do()

            period = max(DAY, self.cd_notify.cooldown)
            event = await self.data_source.get_savers_event_cached(period)
            if not event:
                self.logger.warning('Failed to load Savers data!')
                return

            savers = event.current_stats
            self.logger.info(f'Finished loading saver stats: '
                             f'{savers.total_unique_savers} total savers, '
                             f'avg APR = {savers.average_apr:.02f}% '
                             f'total saved = {short_dollar(savers.total_usd_saved)}')

            await self.pass_data_to_listeners(event)
