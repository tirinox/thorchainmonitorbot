from typing import NamedTuple, List, Optional

from semver import VersionInfo

from .node_info import NodeSetChanges, NodeVersionConsensus


class AlertVersionUpgradeProgress(NamedTuple):
    data: NodeSetChanges
    ver_con: NodeVersionConsensus


class AlertVersionChanged(NamedTuple):
    data: NodeSetChanges
    new_versions: List[VersionInfo]
    old_active_ver: Optional[VersionInfo]
    new_active_ver: Optional[VersionInfo]

