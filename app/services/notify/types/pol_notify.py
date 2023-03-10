from typing import Optional

from aiothornode.types import ThorPOL, thor_to_float, THOR_BASIS_POINT_MAX

from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.mimir_naming import MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT, MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH
from services.models.pol import EventPOL, POLState
from services.models.time_series import TimeSeries


class POLNotifier(WithDelegates, INotified, WithLogger):
    MIN_DURATION = DAY

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cd = parse_timespan_to_seconds(deps.cfg.pol.notification.cooldown)
        self._allow_when_zero = bool(deps.cfg.pol.notification.allow_when_zero)
        self.spam_cd = Cooldown(self.deps.db, 'POL', cd)
        self.ts = TimeSeries('POL', self.deps.db)
        self.last_event: Optional[EventPOL] = None

    async def find_stats_ago(self, period_ago) -> Optional[POLState]:
        # todo!
        data = await self.ts.get_best_point_ago(period_ago, tolerance_percent=1.0, is_json=True)
        # noinspection PyArgumentList
        return ThorPOL(**data[0]) if data[0] else None

    async def _record_pol(self, event: EventPOL):
        data = event.current._asdict()
        # todo: add pool membership!
        await self.ts.add_as_json(data)

    async def _enrich_data(self, event: EventPOL):
        ago_seconds = max(self.spam_cd.cooldown, self.MIN_DURATION)
        previous_data = await self.find_stats_ago(ago_seconds)
        mimir = self.deps.mimir_const_holder

        synth_target = mimir.get_constant(MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH, 4500)
        synth_target = thor_to_float(synth_target) / THOR_BASIS_POINT_MAX * 100.0

        event = event._replace(
            previous=previous_data,
            prices=self.deps.price_holder,
            mimir_max_deposit=thor_to_float(mimir.get_constant(MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT, 10e3, float)),
            mimir_synth_target_ptc=synth_target,
        )
        return event

    async def on_data(self, sender, event: EventPOL):
        if not self._allow_when_zero and event.current.is_zero:
            self.logger.warning('Got zero POL, ignoring it...')
            return

        event = await self._enrich_data(event)
        self.last_event = event
        # todo: record POL state in the DB

        if await self.spam_cd.can_do():
            await self.spam_cd.do()
            await self.pass_data_to_listeners(event)
