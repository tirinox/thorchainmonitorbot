from typing import List

from services.lib.date_utils import MINUTE
from services.lib.depcont import DepContainer
from services.models.node_info import NodeEvent, EventDataVariation, NodeEventType
from services.models.thormon import ThorMonNodeTimeSeries, get_last_thormon_node_state
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting


class SlashPointTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_node_events(self, node_address, telemetry: ThorMonNodeTimeSeries) -> List[NodeEvent]:
        slash_curve = [(t, node.slash_points) for t, node in telemetry]
        if len(slash_curve) >= 2:
            slash_start = slash_curve[0][1]
            slash_end = slash_curve[-1][1]
            if slash_end != slash_start:
                last_state = get_last_thormon_node_state(telemetry)
                data = EventDataVariation(slash_curve)
                return [NodeEvent(node_address, NodeEventType.SLASHING, data, thor_node=last_state, tracker=self)]
        return []

    async def is_event_ok(self, event: NodeEvent, settings: dict) -> bool:
        if bool(settings.get(NodeOpSetting.SLASH_ON, True)):
            return False
        # todo

        threshold = settings.get(NodeOpSetting.SLASH_THRESHOLD, 50)
        interval = settings.get(NodeOpSetting.SLASH_PERIOD, 5 * MINUTE)
        # fixme!

        return True
