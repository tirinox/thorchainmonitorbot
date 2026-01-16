from typing import Optional, List, Tuple

from lib.date_utils import DAY
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.runepool import AlertPOLState
from models.time_series import TimeSeries


class POLStateRecorder(WithLogger, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.ts = TimeSeries('POL', self.deps.db)
        self.last_event: Optional[AlertPOLState] = None
        self.prev_state_ago_sec = DAY

    async def record_pol_state(self, pol_state: AlertPOLState):
        try:
            data = pol_state.to_dict()
            await self.ts.add_as_json(data)
        except Exception as e:
            self.logger.exception(f'Failed to add a point to the POL time series: {e}')

    async def find_stats_ago(self, period_ago) -> Optional[AlertPOLState]:
        data, _ = await self.ts.get_best_point_ago(period_ago, tolerance_percent=1.0, is_json=True)
        try:
            if data:
                return AlertPOLState.load_from_series(data)
        except Exception as e:
            self.logger.exception(f'Error loading EventPOL: {e}')
            return None

    async def last_points(self, period_ago) -> List[Tuple[float, AlertPOLState]]:
        try:
            data = await self.ts.get_last_values_json(period_ago, with_ts=True)
            return [
                (ts, AlertPOLState.load_from_series(j)) for ts, j in data
            ]
        except Exception as e:
            self.logger.exception(f'Error loading last EventPOL: {e}')
            return []

    async def on_data(self, sender, event: AlertPOLState):
        if event.current.is_zero:
            self.logger.warning('Got zero POL, ignoring it...')
            return

        previous_data = await self.find_stats_ago(self.prev_state_ago_sec)

        if previous_data:
            event = event._replace(previous=previous_data.current)

        self.last_event = event
        await self.record_pol_state(event)
