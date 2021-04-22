from dataclasses import dataclass
from typing import List

from services.models.base import BaseModelMixin


@dataclass
class NodeInfo(BaseModelMixin):
    ACTIVE = 'Active'
    STANDBY = 'Standby'

    status: str = ''

    node_address: str = ''
    bond: int = 0
    ip_address: str = ''

    version: str = ''
    slash_points: int = 0

    # there are not all properties

    @property
    def is_active(self):
        return self.status == self.ACTIVE

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
