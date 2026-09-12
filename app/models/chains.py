from dataclasses import dataclass, field
from typing import Dict, List, Optional

from api.aionode.types import ThorChainInfo
from lib.constants import Chains
from models.asset import Asset


@dataclass
class ChainInfoHolder:
    OK = 'ok'
    WARNING = 'warning'
    HALTED = 'halted'

    state_dict: Dict[str, ThorChainInfo] = field(default_factory=dict)

    @classmethod
    def from_list(cls, chain_info_dict):
        return cls(state_dict=chain_info_dict)

    @property
    def all_chains(self):
        return list(self.state_dict.keys())

    @property
    def active_chains(self):
        return [chain for chain, info in self.state_dict.items() if info.is_perfect]

    @property
    def halted_chains(self):
        return [chain for chain, info in self.state_dict.items() if info.halted]

    @property
    def state_list(self):
        return [
            (chain, self.one_work_chain_state(info))
            for chain, info in self.state_dict.items()
        ]

    @classmethod
    def one_work_chain_state(cls, info: ThorChainInfo):
        if info.halted or info.chain_trading_paused or info.global_trading_paused:
            return cls.HALTED
        if info.chain_lp_actions_paused:
            return cls.WARNING
        else:
            return cls.OK


class ChainAspect:
    """One column of the network status table."""

    SCANNING = 'scanning'
    TRADING = 'trading'
    LP = 'lp'
    SIGNING = 'signing'

    ALL = (SCANNING, TRADING, LP, SIGNING)

    TITLES = {
        SCANNING: 'Scanning',
        TRADING: 'Trading',
        LP: 'LP',
        SIGNING: 'Signing',
    }


class AspectState:
    AVAILABLE = 'available'
    PAUSED = 'paused'
    UNKNOWN = 'unknown'


@dataclass
class ChainAspectStatus:
    """State of one cell of the network status table."""

    state: str = AspectState.UNKNOWN
    incident_ago: Optional[float] = None
    """Seconds since the last incident, if it happened inside the "recent" window."""

    @property
    def is_paused(self):
        return self.state == AspectState.PAUSED

    @property
    def is_unstable(self):
        """Available right now, but it was paused recently. Rendered as a yellow dot."""
        return self.state == AspectState.AVAILABLE and self.incident_ago is not None

    def to_dict(self):
        return {
            'state': self.state,
            'unstable': self.is_unstable,
            'incident_ago': self.incident_ago,
        }


@dataclass
class ChainStatusRow:
    """One row of the network status table: a chain and all of its aspects."""

    chain: str
    aspects: Dict[str, ChainAspectStatus] = field(default_factory=dict)
    changed: bool = False
    """True if this very chain has just changed its halt state (it caused the alert)."""

    @property
    def logo(self):
        if self.chain == Chains.BASE:
            return Chains.BASE  # Base has ETH as its gas asset, but we wanna show the BASE logo here
        return str(Asset.gas_asset_from_chain(self.chain))

    @property
    def is_paused(self):
        return any(a.is_paused for a in self.aspects.values())

    @property
    def is_unstable(self):
        return any(a.is_unstable for a in self.aspects.values())

    def to_dict(self):
        return {
            'chain': self.chain,
            'logo': self.logo,
            'changed': self.changed,
            'paused': self.is_paused,
            'unstable': self.is_unstable,
            'aspects': {name: aspect.to_dict() for name, aspect in self.aspects.items()},
        }


@dataclass
class ChainStatusTable:
    """Full network status snapshot: everything the "trading halt" infographic needs."""

    OPERATIONAL = 'operational'
    DEGRADED = 'degraded'
    UNSTABLE = 'unstable'

    rows: List[ChainStatusRow] = field(default_factory=list)
    recent_window_sec: float = 0.0
    """How long an incident is remembered and shown as a yellow dot."""

    @property
    def paused_chains(self) -> List[str]:
        return [row.chain for row in self.rows if row.is_paused]

    @property
    def unstable_chains(self) -> List[str]:
        return [row.chain for row in self.rows if row.is_unstable and not row.is_paused]

    @property
    def overall_status(self):
        if self.paused_chains:
            return self.DEGRADED
        elif self.unstable_chains:
            return self.UNSTABLE
        else:
            return self.OPERATIONAL

    def to_dict(self):
        return {
            'columns': [
                {'key': key, 'title': ChainAspect.TITLES[key]}
                for key in ChainAspect.ALL
            ],
            'chains': [row.to_dict() for row in self.rows],
            'total_chains': len(self.rows),
            'paused_chains': self.paused_chains,
            'unstable_chains': self.unstable_chains,
            'overall_status': self.overall_status,
            'recent_window_sec': self.recent_window_sec,
        }
