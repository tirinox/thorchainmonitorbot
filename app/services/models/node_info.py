import json
import random
import re
import secrets
from collections import Counter
from dataclasses import dataclass, field
from statistics import median
from typing import List, Dict, NamedTuple, Optional, Tuple, Any

from semver import VersionInfo

from services.lib.constants import thor_to_float
from services.lib.date_utils import now_ts
from services.lib.texts import find_country_emoji
from services.models.base import BaseModelMixin
from services.models.thormon import ThorMonNode

ZERO_VERSION = VersionInfo(0, 0, 0)


@dataclass
class NodeInfo(BaseModelMixin):
    ACTIVE = 'Active'
    STANDBY = 'Standby'
    READY = 'Ready'
    WHITELISTED = 'Whitelisted'
    DISABLED = 'Disabled'

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
    status_since: int = 0
    observe_chains: List = field(default_factory=list)
    jail: Dict = field(default_factory=dict)

    ip_info: Dict[str, Any] = field(default_factory=dict)

    @property
    def rune_bond_float(self):
        return thor_to_float(self.bond)

    @property
    def chain_dict(self):
        return {c['chain']: c['height'] for c in self.observe_chains} if self.observe_chains else {}

    @property
    def status_capitalized(self):
        return self.status.capitalize()

    @property
    def parsed_version(self) -> VersionInfo:
        try:
            return VersionInfo.parse(self.version)
        except ValueError:
            return ZERO_VERSION

    @property
    def is_active(self):
        return self.status_capitalized == self.ACTIVE

    @property
    def is_standby(self):
        return self.status_capitalized == self.STANDBY or self.status_capitalized == self.READY

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
            bond=int(thor_to_float(d.get('bond', 0))),
            ip_address=d.get('ip_address', ''),
            version=d.get('version', ''),
            slash_points=int(d.get('slash_points', 0)),
            current_award=thor_to_float(d.get('current_award', 0.0)),
            requested_to_leave=bool(d.get('requested_to_leave', False)),
            forced_to_leave=bool(d.get('forced_to_leave', False)),
            active_block_height=int(d.get('active_block_height', 0)),
            status_since=int(d.get('status_since', 0)),
            observe_chains=d.get('observe_chains', []),
            jail=d.get('jail', {}),
        )

    @staticmethod
    def fake_node(status=ACTIVE, address=None, bond=None, ip=None, version='54.1', slash=0):
        r = lambda: random.randint(1, 255)
        ip = ip if ip is not None else f'{r()}.{r()}.{r()}.{r()}'
        address = address if address is not None else f'thor{secrets.token_hex(32)}'
        bond = bond if bond is not None else random.randint(1, 2_000_000)
        return NodeInfo(status, address, bond, ip, version, slash)

    @property
    def flag_emoji(self) -> str:
        if self.ip_info:
            return find_country_emoji(self.ip_info.get('country', ''))
        return ''


class NodeVersionConsensus(NamedTuple):
    ratio: float
    top_version: VersionInfo
    top_version_count: int
    total_active_node_count: int


MapAddressToPrevAndCurrNode = Dict[str, Tuple[NodeInfo, NodeInfo]]


@dataclass
class NodeListHolder:
    nodes: List[NodeInfo] = field(default_factory=list)

    @property
    def active_nodes(self):
        return [n for n in self.nodes if n.is_active]

    def is_ip_nodes(self, ip_address):
        return any(ip_address == n.ip_address for n in self.nodes)


@dataclass
class NodeSetChanges:
    nodes_added: List[NodeInfo] = field(default_factory=list)
    nodes_removed: List[NodeInfo] = field(default_factory=list)
    nodes_activated: List[NodeInfo] = field(default_factory=list)
    nodes_deactivated: List[NodeInfo] = field(default_factory=list)
    nodes_all: List[NodeInfo] = field(default_factory=list)  # all current nodes
    nodes_previous: List[NodeInfo] = field(default_factory=list)  # previous node set

    @classmethod
    def empty(cls):
        return cls()

    @property
    def is_empty(self):
        return self.count_of_changes == 0

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

    @property
    def all_affected_nodes(self):
        return self.nodes_added + self.nodes_removed + self.nodes_activated + self.nodes_deactivated

    @property
    def active_only_nodes(self) -> List[NodeInfo]:
        return [n for n in self.nodes_all if n.is_active]

    @property
    def previous_active_only_nodes(self) -> List[NodeInfo]:
        return [n for n in self.nodes_previous if n.is_active]

    @staticmethod
    def minimal_active_version(node_list) -> VersionInfo:
        """
        THORChain run min versions among all active nodes.
        """
        if not node_list:
            return ZERO_VERSION

        min_ver = node_list[0].parsed_version
        for node in node_list:
            cur_ver = node.parsed_version
            if cur_ver < min_ver:
                min_ver = cur_ver
        return min_ver

    @staticmethod
    def version_set(nodes: List[NodeInfo]):
        return {n.parsed_version for n in nodes if n.parsed_version != ZERO_VERSION}

    @staticmethod
    def find_nodes_with_version(nodes: List[NodeInfo], v: VersionInfo) -> List[NodeInfo]:
        if isinstance(v, VersionInfo):
            return [n for n in nodes if n.parsed_version == v]
        else:
            return [n for n in nodes if n.version == v]

    @staticmethod
    def version_counter(nodes: List[NodeInfo]):
        return Counter(n.parsed_version for n in nodes)

    @staticmethod
    def count_version(nodes: List[NodeInfo], v: VersionInfo):
        return sum(1 for n in nodes if n.parsed_version == v)

    @property
    def max_active_version(self):
        return max(n.parsed_version for n in self.active_only_nodes)

    @property
    def max_available_version(self):
        return max(n.parsed_version for n in self.nodes_all)

    @property
    def current_active_version(self):
        return self.minimal_active_version(self.active_only_nodes)

    @property
    def new_versions(self):
        old_ver_set = self.version_set(self.nodes_previous)
        new_ver_set = self.version_set(self.nodes_all)
        new_versions = new_ver_set - old_ver_set
        return list(sorted(new_versions))

    @property
    def version_consensus(self) -> Optional[NodeVersionConsensus]:
        """
        Most popular version node count / Active node count = 0..1
        1 = all run the same version
        0 = no nodes at all
        """
        active_nodes = self.active_only_nodes
        if not active_nodes:
            return

        counter = self.version_counter(active_nodes)
        top_version = self.max_active_version
        top_count = counter[top_version]
        ratio = top_count / len(active_nodes)
        return NodeVersionConsensus(ratio, top_version, top_count, len(active_nodes))

    @staticmethod
    def node_map(nodes: List[NodeInfo]):
        return {n.node_address: n for n in nodes}

    @property
    def prev_and_curr_node_map(self) -> MapAddressToPrevAndCurrNode:
        old = self.node_map(self.nodes_previous)
        new = self.node_map(self.nodes_all)

        common_addresses = set(new.keys()) & set(old.keys())
        return {address: (old[address], new[address]) for address in common_addresses}

    @property
    def bond_churn_in(self):
        return sum(node.bond for node in self.nodes_activated)

    @property
    def bond_churn_out(self):
        return sum(node.bond for node in self.nodes_deactivated)

    @property
    def bond_churn_delta(self):
        return self.bond_churn_in - self.bond_churn_out


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

    @property
    def not_active_nodes(self):
        return [n for n in self.node_info_list if not n.is_active]

    def select_ip_info_for_nodes(self, nodes: List[NodeInfo]) -> List[dict]:
        return [self.ip_info_dict.get(n.ip_address, None) for n in nodes]

    def get_general_provider(self, data: dict):
        org = data.get('org')
        if org is None:
            return self.UNKNOWN_PROVIDER
        try:
            components = re.split('[ -]', org)
        except TypeError:
            return self.UNKNOWN_PROVIDER

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

    @staticmethod
    def get_min_median_max_bond(nodes: List[NodeInfo]) -> Tuple[float, float, float]:
        if not nodes:
            return 0, 0, 0
        bonds = [n.rune_bond_float for n in nodes]
        return min(bonds), median(bonds), max(bonds)


class EventNodeOnline(NamedTuple):
    online: bool
    duration: float
    service: str


class EventBlockHeight(NamedTuple):
    chain: str
    expected_block: int = 0
    actual_block: int = 0
    how_long_behind: float = 0.0
    is_sync: bool = False

    @property
    def block_lag(self):
        return self.expected_block - self.actual_block


class EventDataVariation(NamedTuple):
    points: List[Tuple[float, Any]]

    def get_point_ago(self, seconds_ago):
        t0 = now_ts() - seconds_ago
        for t, v in reversed(self.points):
            if t < t0:
                return t, v
        return self.points[0] if self.points else 0, 0


class EventDataSlash(NamedTuple):
    previous_pts: int
    current_pts: int
    interval_sec: float

    @property
    def delta_pts(self):
        return abs(self.current_pts - self.previous_pts)


class NodeEventType:
    VERSION_CHANGED = 'version_change'
    NEW_VERSION_DETECTED = 'new_version'
    SLASHING = 'slashing'
    CHURNING = 'churning'
    BOND = 'bond'
    IP_ADDRESS_CHANGED = 'ip_address'
    SERVICE_ONLINE = 'service_online'
    BLOCK_HEIGHT = 'block_height'
    PRESENCE = 'presence'

    CABLE_DISCONNECT = 'disconnected'
    CABLE_RECONNECT = 'reconnected'

    TEXT_MESSAGE = 'message_txt'


class NodeEvent(NamedTuple):
    address: str
    type: str
    data: Any
    single_per_user: bool = False
    node: NodeInfo = None
    thor_node: ThorMonNode = None
    tracker: object = None

    ANY = '*'

    @property
    def is_broad(self):
        return self.address == self.ANY
