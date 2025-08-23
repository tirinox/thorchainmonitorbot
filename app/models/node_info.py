import json
import random
import secrets
import typing
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import List, Dict, NamedTuple, Optional, Tuple, Any, Iterator

from semver import VersionInfo

from lib.constants import thor_to_float, float_to_thor, bp_to_float
from lib.date_utils import now_ts
from lib.money import calculate_apy
from lib.texts import find_country_emoji
from lib.thor_logic import get_effective_security_bond
from models.geo_ip import LocationInfo
from .base import BaseModelMixin

ZERO_VERSION = VersionInfo(0)


class BondProvider(typing.NamedTuple):
    address: str
    rune_bond: float
    is_node_operator: bool = False
    anticipated_award: float = 0.0
    bond_share: float = 0.0
    fee_rate: float = 0.0  # 0..1


@dataclass
class NodeInfo(BaseModelMixin):
    ACTIVE = 'Active'
    STANDBY = 'Standby'
    READY = 'Ready'
    WHITELISTED = 'Whitelisted'
    DISABLED = 'Disabled'

    status: str = ''

    node_address: str = ''
    bond: float = 0.0
    ip_address: str = ''

    version: str = ''
    slash_points: int = 0

    current_award: float = 0.0

    bond_providers: List[BondProvider] = field(default_factory=list)
    node_operator_fee: float = 0.0
    node_operator: str = ''

    # new fields
    requested_to_leave: bool = False
    forced_to_leave: bool = False
    active_block_height: int = 0
    status_since: int = 0
    observe_chains: List = field(default_factory=list)
    jail: Dict = field(default_factory=dict)

    ip_info: Optional[LocationInfo] = None

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

    @staticmethod
    def _make_bond_provider(raw, total_bond, fee_rate, node_op_address, total_reward: float) -> BondProvider:
        bond = float(thor_to_float(raw['bond']))
        bond_share = bond / total_bond

        anticipated_award = bond_share * total_reward * (1.0 - fee_rate)

        address = raw['bond_address']
        if address == node_op_address:
            # The node operator also gets entire fees in addition to normal BP award, right?
            anticipated_award += total_reward * fee_rate

        return BondProvider(
            address=address,
            rune_bond=bond,
            is_node_operator=(address == node_op_address),
            anticipated_award=anticipated_award,
            bond_share=bond_share,
            fee_rate=fee_rate,
        )

    @classmethod
    def from_json(cls, jstr):
        if not jstr:
            return None
        d = json.loads(jstr) if isinstance(jstr, (str, bytes)) else jstr
        node_operator = d.get('node_operator_address', '')
        bond_provider_info = d.get('bond_providers', {})
        total_bond = float(thor_to_float(d.get('total_bond', 0)))
        bond_prov_fee_rate = bp_to_float(bond_provider_info.get('node_operator_fee', 0))
        node_address = d.get('node_address', '')
        current_award = thor_to_float(d.get('current_award', 0.0))
        return cls(
            status=d.get('status', NodeInfo.DISABLED),
            node_address=node_address,
            bond=total_bond,
            ip_address=d.get('ip_address', ''),
            version=d.get('version', ''),
            slash_points=int(d.get('slash_points', 0)),
            current_award=current_award,
            requested_to_leave=bool(d.get('requested_to_leave', False)),
            forced_to_leave=bool(d.get('forced_to_leave', False)),
            active_block_height=int(d.get('active_block_height', 0)),
            status_since=int(d.get('status_since', 0)),
            observe_chains=d.get('observe_chains', []),
            jail=d.get('jail', {}),
            bond_providers=[
                cls._make_bond_provider(prov, total_bond, bond_prov_fee_rate, node_operator, current_award)
                for prov in (bond_provider_info.get('providers') or [])
            ],
            node_operator=node_operator,
            node_operator_fee=bond_prov_fee_rate
        )

    @classmethod
    def from_db(cls, data):
        instance = cls(**data)
        # fix bond_providers by converting [str, float] to BondProvider
        instance.bond_providers = [BondProvider(*arr) for arr in instance.bond_providers]
        return instance

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
            return find_country_emoji(self.ip_info.country_name or '')
        return ''


class NodeVersionConsensus(NamedTuple):
    ratio: float
    top_version: VersionInfo
    top_version_count: int
    total_active_node_count: int


MapAddressToPrevAndCurrNode = Dict[str, Tuple[NodeInfo, NodeInfo]]


class EventBondProviderPayout(NamedTuple):
    node_address: str
    bond_provider: BondProvider
    rune_payout: float


class EventBondProviderInOut(NamedTuple):
    node_address: str
    bond_provider: BondProvider
    is_out: bool

    @property
    def is_in(self):
        return not self.is_out


@dataclass
class NodeSetChanges:
    nodes_added: List[NodeInfo] = field(default_factory=list)
    nodes_removed: List[NodeInfo] = field(default_factory=list)
    nodes_activated: List[NodeInfo] = field(default_factory=list)
    nodes_deactivated: List[NodeInfo] = field(default_factory=list)
    nodes_all: List[NodeInfo] = field(default_factory=list)  # all current nodes
    nodes_previous: List[NodeInfo] = field(default_factory=list)  # previous node set

    vaults_migrating: bool = False
    block_no: int = 0
    churn_duration: float = 0.0

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
        return not self.has_churn_happened and all_add_removed_are_strange

    @property
    def has_churn_happened(self):
        return bool(self.nodes_activated or self.nodes_deactivated)

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
            return None

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

    def __str__(self) -> str:
        return (f"NodeSetChanges("
                f"added={len(self.nodes_added)}, "
                f"removed={len(self.nodes_removed)}, "
                f"activated={len(self.nodes_activated)}, "
                f"deactivated={len(self.nodes_deactivated)})")

    @property
    def bond_providers_churns(self):
        return [
            EventBondProviderInOut(node.node_address, bp, is_out=(not node.is_active))
            for node in self.nodes_activated + self.nodes_deactivated
            for bp in node.bond_providers
        ]

    @property
    def bond_providers_churns_by_address(self):
        # why don't you use groupby?
        addr2events = defaultdict(list)
        for ev in self.bond_providers_churns:
            addr2events[ev.bond_provider.address].append(ev)
        return addr2events


@dataclass
class NetworkNodes:
    node_info_list: List[NodeInfo] = field(default_factory=list)
    ip_info_dict: Dict[str, dict] = field(default_factory=dict)  # IP -> Geo Info
    total_rune_supply: float = 425e6  # todo: set it correctly dynamically

    def __len__(self):
        return len(self.node_info_list)

    def __bool__(self):
        return bool(self.node_info_list)

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

    def is_ip_nodes(self, ip_address):
        return any(ip_address == n.ip_address for n in self.node_info_list)

    @staticmethod
    def calculate_security_cap_rune(nodes, full=False):
        active_bonds = [float_to_thor(node.bond) for node in nodes if node.is_active]
        if full:
            cap = sum(active_bonds)
        else:
            cap = get_effective_security_bond(active_bonds)
        return thor_to_float(cap)

    def find_bond_providers(self, address: str) -> Iterator[Tuple[NodeInfo, BondProvider]]:
        for node in self.node_info_list:
            for bp in node.bond_providers:
                if bp.address == address:
                    yield node, bp

    @staticmethod
    def get_min_median_max_total_bond(nodes: List[NodeInfo]) -> Tuple[float, float, float, float]:
        if not nodes:
            return 0, 0, 0, 0
        bonds = [n.bond for n in nodes]
        return min(bonds), median(bonds), max(bonds), sum(bonds)

    def sort_by_status(self):
        self.node_info_list.sort(key=lambda n: n.status, reverse=True)

    @property
    def total_bond(self):
        return sum(n.bond for n in self.node_info_list)

    @property
    def ip_addresses(self):
        return [node.ip_address for node in self.node_info_list]


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


class EventNodeFeeChange(NamedTuple):
    bond_provider: str
    previous: float
    current: float


class EventProviderBondChange(NamedTuple):
    bond_provider: str
    prev_bond: float
    curr_bond: float
    on_churn: bool

    duration_sec: float = 0

    @property
    def apy(self):
        if self.prev_bond and self.duration_sec and self.on_churn:
            apy = calculate_apy(self.prev_bond, self.curr_bond, self.duration_sec)
            if apy < 10_000:
                return apy


class EventProviderStatus(NamedTuple):
    bond_provider: str
    bond: float
    appeared: bool
    previous_status: str = None
    previous_ts: float = 0

    @property
    def duration(self) -> float:
        return now_ts() - self.previous_ts if self.previous_ts else 0


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

    # bond provider tools:
    FEE_CHANGE = 'fee_change'
    BOND_CHANGE = 'bond_change'
    BP_PRESENCE = 'bp_presence'


class NodeEvent(NamedTuple):
    address: str
    type: str
    data: Any
    single_per_user: bool = False
    node: NodeInfo = None
    tracker: object = None
    usd_per_rune: float = 0.0

    ANY = '*'

    @property
    def is_broad(self):
        return self.address == self.ANY

    @classmethod
    def new(cls, node: NodeInfo, ev_type, data):
        return cls(node.node_address, ev_type, data, node=node)

    def __str__(self):
        return f'NodeEvent({self.address}, type={self.type}, data={self.data})'


class NodeStatsItem(typing.NamedTuple):
    ts: float
    bond_min: float
    bond_median: float
    bond_max: float
    bond_active_total: float
    bond_total: float
    n_nodes: float
    n_active_nodes: float

    @classmethod
    def from_json(cls, j):
        ts, data = j
        return cls(
            ts=ts,
            bond_min=float(data.get('bond_min', 0.0)),
            bond_median=float(data.get('bond_med', 0.0)),
            bond_max=float(data.get('bond_max', 0.0)),
            bond_active_total=float(data.get('bond_active_total', 0.0)),
            bond_total=float(data.get('bond_total', 0.0)),
            n_nodes=int(data.get('n_nodes', 0)),
            n_active_nodes=int(data.get('n_active_nodes', 0)),
        )

    @property
    def is_valid(self):
        return self.n_active_nodes > 0 and self.bond_active_total > 0


class AlertNodeChurn(NamedTuple):
    changes: NodeSetChanges
    finished: bool
    with_picture: bool
    network_info: Optional[NetworkNodes] = None
    bond_chart: Optional[List[NodeStatsItem]] = None
