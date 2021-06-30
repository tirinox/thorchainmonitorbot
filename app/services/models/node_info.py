import json
import re
from dataclasses import dataclass, field
from typing import List, Dict

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

    @property
    def is_nonsense(self):
        all_add_removed_are_strange = all(
            node.in_strange_status for node in (self.nodes_added + self.nodes_removed)
        )
        return not self.nodes_activated and not self.nodes_deactivated and all_add_removed_are_strange

    @property
    def count_of_changes(self):
        return (
                len(self.nodes_added) +
                len(self.nodes_activated) +
                len(self.nodes_deactivated) +
                len(self.nodes_removed)
        )


@dataclass
class NetworkNodeIpInfo:
    UNKNOWN_PROVIDER = 'Unknown'

    node_info_list: List[NodeInfo] = field(default_factory=list)
    ip_info_dict: Dict[str, dict] = field(default_factory=dict)  # IP -> Geo Info

    @property
    def standby_nodes(self):
        return [n for n in self.node_info_list if n.is_standby]

    @property
    def active_nodes(self):
        return [n for n in self.node_info_list if n.is_active]

    def select_ip_info_for_nodes(self, nodes: List[NodeInfo]) -> List[dict]:
        return [self.ip_info_dict.get(n.ip_address, None) for n in nodes]

    @staticmethod
    def get_general_provider(data: dict):
        org = data.get('org', '')
        components = re.split('[ -]', org)
        if components:
            return str(components[0]).upper()
        return org

    def get_providers(self, nodes: List[NodeInfo] = None) -> List[str]:
        if not nodes:
            nodes = self.node_info_list  # all nodes from this class

        providers = []
        for node in nodes:
            ip_info = self.ip_info_dict.get(node.ip_address, None)
            if ip_info:
                providers.append(self.get_general_provider(ip_info))
            else:
                providers.append(self.UNKNOWN_PROVIDER)

        return providers
