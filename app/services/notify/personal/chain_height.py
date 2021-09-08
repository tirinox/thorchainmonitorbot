from typing import List

from services.lib.depcont import DepContainer
from services.models.thormon import ThorMonNodeTimeSeries
from services.notify.personal.telemetry import NodeTelemetryDatabase
from services.notify.personal.models import BaseChangeTracker
from services.models.node_info import NodeChange

TRIGGER_SWITCH_CD = 30.0  # sec


class ChainHeightTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_node_changes(self, node_address, telemetry: ThorMonNodeTimeSeries):
        if not node_address:
            return []

        changes = []

        return changes

    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return await super().filter_changes(ch_list, settings)
