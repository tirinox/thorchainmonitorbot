from dataclasses import dataclass
from typing import List

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

    current_award: float = ''

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
