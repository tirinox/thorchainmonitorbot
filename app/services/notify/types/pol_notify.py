from typing import Optional, List, Tuple

from aiothornode.types import thor_to_float, THOR_BASIS_POINT_MAX

from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, MINUTE
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.mimir_naming import MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT, MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH
from services.models.pol import AlertPOL, POLState
from services.models.time_series import TimeSeries


class POLNotifier(WithDelegates, INotified, WithLogger):
    MIN_DURATION = 1 * MINUTE

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cd = parse_timespan_to_seconds(deps.cfg.pol.notification.cooldown)
        self._allow_when_zero = bool(deps.cfg.pol.notification.allow_when_zero)
        self.spam_cd = Cooldown(self.deps.db, 'POL', cd)
        self.ts = TimeSeries('POL', self.deps.db)
        self.last_event: Optional[AlertPOL] = None

    async def find_stats_ago(self, period_ago) -> Optional[AlertPOL]:
        data, _ = await self.ts.get_best_point_ago(period_ago, tolerance_percent=1.0, is_json=True)
        try:
            if data:
                return AlertPOL.load_from_series(data)
        except Exception as e:
            self.logger.exception(f'Error loading EventPOL: {e}')
            return

    async def last_points(self, period_ago) -> List[Tuple[float, AlertPOL]]:
        try:
            data = await self.ts.get_last_values_json(period_ago, with_ts=True)
            return [
                (ts, self._enrich_data(AlertPOL.load_from_series(j))) for ts, j in data
            ]
        except Exception as e:
            self.logger.exception(f'Error loading last EventPOL: {e}')
            return []

    async def _record_pol(self, event: AlertPOL):
        try:
            data = event.to_json_for_series
            await self.ts.add_as_json(data)
        except Exception as e:
            self.logger.exception(f'Failed to add a point to the POL time series: {e}')

    def _enrich_data(self, event: AlertPOL, previous_data: Optional[POLState] = None):
        mimir = self.deps.mimir_const_holder

        synth_target = mimir.get_constant(MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH, 4500)
        synth_target = thor_to_float(synth_target) / THOR_BASIS_POINT_MAX * 100.0

        event = event._replace(
            previous=previous_data or event.previous,
            prices=self.deps.price_holder,
            mimir_max_deposit=thor_to_float(mimir.get_constant(MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT, 10e3, float)),
            mimir_synth_target_ptc=synth_target,
        )
        return event

    async def on_data(self, sender, event: AlertPOL):
        ago_seconds = max(self.spam_cd.cooldown, self.MIN_DURATION)
        previous_data = await self.find_stats_ago(ago_seconds)

        event = self._enrich_data(event, previous_data.current if previous_data else None)

        self.last_event = event

        await self._record_pol(event)

        if not self._allow_when_zero and event.current.is_zero:
            self.logger.warning('Got zero POL, ignoring it...')
            return

        if await self.spam_cd.can_do():
            await self.spam_cd.do()
            await self.pass_data_to_listeners(event)
