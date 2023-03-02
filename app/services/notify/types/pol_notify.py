from typing import Optional

from aiothornode.types import ThorPOL

from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.time_series import TimeSeries


class POLNotifier(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cd = parse_timespan_to_seconds(deps.cfg.pol.notification.cooldown)
        self.spam_cd = Cooldown(self.deps.db, 'POLReport', cd)
        self.ts = TimeSeries('POL', self.deps.db)

    async def find_stats_ago(self, period_ago) -> Optional[ThorPOL]:
        data = await self.ts.get_best_point_ago(period_ago, tolerance_percent=1.0, is_json=True)
        # noinspection PyArgumentList
        return ThorPOL(**data[0]) if data[0] else None

    async def on_data(self, sender, data: ThorPOL):
        await self.ts.add_as_json(data._asdict())

        r = await self.find_stats_ago(30)
        print(r)

        if await self.spam_cd.can_do():
            await self.spam_cd.do()

            # await self.pass_data_to_listeners(report)
