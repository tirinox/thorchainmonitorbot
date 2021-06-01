import json
from dataclasses import dataclass, field
from typing import List

from services.lib.constants import THOR_DIVIDER_INV
from services.models.base import BaseModelMixin


@dataclass
class NodeInfo(BaseModelMixin):
    ACTIVE = 'active'
    STANDBY = 'standby'
    WHITELISTED = 'whitelisted'
    DISABLED = 'disabled'

    status: str = ''

    node_address: str = ''
    bond: int = 0
    ip_address: str = ''

    version: str = ''
    slash_points: int = 0

    current_award: float = 0.0

    # new fields
    requested_to_leave: bool = False
    forced_to_leave: bool = False
    active_block_height: int = 0
    observe_chains: List = field(default_factory=list)

    # there are not all properties

    @property
    def is_active(self):
        return self.status.lower() == self.ACTIVE

    @property
    def is_standby(self):
        return self.status.lower() == self.STANDBY

    @property
    def in_strange_status(self):
        return not self.is_standby and not self.is_active

    @property
    def ident(self):
        return self.node_address

    @classmethod
    def from_json(cls, jstr):
        if not jstr:
            return None
        d = json.loads(jstr) if isinstance(jstr, (str, bytes)) else jstr
        return cls(
            status=d.get('status', NodeInfo.DISABLED),
            node_address=d.get('node_address', ''),
            bond=int(d.get('bond', 0)) * THOR_DIVIDER_INV,
            ip_address=d.get('ip_address', ''),
            version=d.get('version', ''),
            slash_points=int(d.get('slash_points', 0)),
            current_award=int(d.get('current_award', 0.0)) * THOR_DIVIDER_INV,
            requested_to_leave=bool(d.get('requested_to_leave', False)),
            forced_to_leave=bool(d.get('forced_to_leave', False)),
            active_block_height=int(d.get('active_block_height', 0)),
            observe_chains=d.get('observe_chains', [])
        )


@dataclass
class NodeInfoChanges:
    nodes_added: List[NodeInfo]
    nodes_removed: List[NodeInfo]
    nodes_activated: List[NodeInfo]
    nodes_deactivated: List[NodeInfo]
    nodes_all: List[NodeInfo]  # all current nodes

    @classmethod
    def empty(cls):
        return cls([], [], [], [], [])

    @property
    def is_empty(self):
        return (not self.nodes_removed and
                not self.nodes_added and
                not self.nodes_activated and
                not self.nodes_deactivated)
