from typing import List

from lib.depcont import DepContainer
from models.node_info import NodeEvent, MapAddressToPrevAndCurrNode, NodeEventType
from .helpers import BaseChangeTracker, NodeOpSetting, DEFAULT_BOND_THRESHOLD_RUNE


class BondTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def get_events_unsafe(self) -> List[NodeEvent]:
        events = list(self._changes_of_bond(self.prev_and_curr_node_map))
        if events:
            usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()
            events = [e._replace(usd_per_rune=usd_per_rune) for e in events]
        return events

    def _changes_of_bond(self, pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.bond != curr.bond:
                yield NodeEvent(prev.node_address, NodeEventType.BOND, (prev.bond, curr.bond),
                                node=curr, tracker=self)

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not bool(settings.get(NodeOpSetting.BOND_ON, True)):
            return False
        old, new = event.data
        threshold = float(settings.get(NodeOpSetting.BOND_THRESHOLD, DEFAULT_BOND_THRESHOLD_RUNE))
        return abs(new - old) >= threshold
