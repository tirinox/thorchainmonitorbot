from typing import Optional, List, Tuple

from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds, MINUTE
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.runepool import AlertPOLState
from models.time_series import TimeSeries


class POLNotifier(WithDelegates, INotified, WithLogger):
    MIN_DURATION = 1 * MINUTE

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.runepool.pol_summary
        cd = parse_timespan_to_seconds(cfg.cooldown)
        self._allow_when_zero = bool(cfg.allow_when_zero)
        self.spam_cd = Cooldown(self.deps.db, 'POL', cd)
        self.ts = TimeSeries('POL', self.deps.db)
        self.last_event: Optional[AlertPOLState] = None

    async def find_stats_ago(self, period_ago) -> Optional[AlertPOLState]:
        data, _ = await self.ts.get_best_point_ago(period_ago, tolerance_percent=1.0, is_json=True)
        try:
            if data:
                return AlertPOLState.load_from_series(data)
        except Exception as e:
            self.logger.exception(f'Error loading EventPOL: {e}')
            return

    async def last_points(self, period_ago) -> List[Tuple[float, AlertPOLState]]:
        try:
            data = await self.ts.get_last_values_json(period_ago, with_ts=True)
            return [
                (ts, AlertPOLState.load_from_series(j)) for ts, j in data
            ]
        except Exception as e:
            self.logger.exception(f'Error loading last EventPOL: {e}')
            return []

    async def _record_pol(self, event: AlertPOLState):
        try:
            data = event.to_json_for_series
            await self.ts.add_as_json(data)
        except Exception as e:
            self.logger.exception(f'Failed to add a point to the POL time series: {e}')

    async def on_data(self, sender, event: AlertPOLState):
        ago_seconds = max(self.spam_cd.cooldown, self.MIN_DURATION)
        previous_data = await self.find_stats_ago(ago_seconds)

        if previous_data:
            event = event._replace(previous=previous_data.current)

        self.last_event = event

        await self._record_pol(event)

        if not self._allow_when_zero and event.current.is_zero:
            self.logger.warning('Got zero POL, ignoring it...')
            return

        if await self.spam_cd.can_do():
            await self.spam_cd.do()
            await self.pass_data_to_listeners(event)
