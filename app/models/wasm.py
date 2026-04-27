from dataclasses import dataclass, field
from typing import List, Dict, Optional

from api.aionode.wasm import WasmCodeInfo


@dataclass
class WasmContractEntry:
    """A single contract instance with its on-chain label and creation block."""
    address: str
    label: str = ''
    block_height: int = 0

    def to_dict(self) -> dict:
        return {'address': self.address, 'label': self.label, 'block_height': self.block_height}

    @classmethod
    def from_dict(cls, d: dict) -> 'WasmContractEntry':
        return cls(
            address=d['address'],
            label=d.get('label', ''),
            block_height=int(d.get('block_height', 0)),
        )


@dataclass
class WasmCodeStats:
    """Stats for a single deployed WASM code ID."""
    code_info: WasmCodeInfo
    contracts: List[WasmContractEntry] = field(default_factory=list)
    # Unix timestamp of when this code_id was first observed by the monitor
    first_seen_ts: float = 0.0

    @property
    def code_id(self) -> int:
        return self.code_info.code_id

    @property
    def creator(self) -> str:
        return self.code_info.creator

    @property
    def data_hash(self) -> str:
        return self.code_info.data_hash

    @property
    def contract_count(self) -> int:
        return len(self.contracts)


@dataclass
class NewWasmDeployments:
    """Result of count_new_deployments(): new codes and contracts over a time window."""
    new_codes: List[WasmCodeStats]
    new_contracts: List[WasmContractEntry]
    days: float

    @property
    def new_codes_count(self) -> int:
        return len(self.new_codes)

    @property
    def new_contracts_count(self) -> int:
        return len(self.new_contracts)

    def __repr__(self) -> str:
        return (
            f"NewWasmDeployments(days={self.days}, "
            f"new_codes={self.new_codes_count}, "
            f"new_contracts={self.new_contracts_count})"
        )


@dataclass
class WasmContractStats:
    """
    Aggregated snapshot of all WASM code variants and their contract instances.
    Returned by WasmCache and refreshed every day.
    """
    codes: List[WasmCodeStats] = field(default_factory=list)

    @property
    def total_codes(self) -> int:
        return len(self.codes)

    @property
    def total_contracts(self) -> int:
        return sum(c.contract_count for c in self.codes)

    @property
    def contracts_per_code(self) -> Dict[int, int]:
        return {c.code_id: c.contract_count for c in self.codes}

    @property
    def all_contracts(self) -> List[WasmContractEntry]:
        """Flat list of every contract entry across all code IDs."""
        return [entry for cs in self.codes for entry in cs.contracts]

    def get_code_stats(self, code_id: int) -> Optional[WasmCodeStats]:
        for c in self.codes:
            if c.code_id == code_id:
                return c
        return None

    def find_label(self, address: str) -> Optional[str]:
        """Return label for a contract address from in-memory data, or None if not found."""
        for cs in self.codes:
            for entry in cs.contracts:
                if entry.address == address:
                    return entry.label
        return None

    def new_contracts_since_block(self, min_block: int) -> List[WasmContractEntry]:
        """All contracts instantiated at block >= min_block."""
        return [e for e in self.all_contracts if e.block_height >= min_block]

    def new_codes_since_ts(self, min_ts: float) -> List[WasmCodeStats]:
        """All code IDs first seen at timestamp >= min_ts."""
        return [cs for cs in self.codes if cs.first_seen_ts >= min_ts]

    def to_dict(self) -> dict:
        return {
            'codes': [
                {
                    'code_info': {
                        'code_id': cs.code_info.code_id,
                        'creator': cs.code_info.creator,
                        'data_hash': cs.code_info.data_hash,
                        'instantiate_permission': {
                            'permission': cs.code_info.instantiate_permission.permission,
                            'addresses': list(cs.code_info.instantiate_permission.addresses),
                        } if cs.code_info.instantiate_permission else {},
                    },
                    'first_seen_ts': cs.first_seen_ts,
                    'contracts': [c.to_dict() for c in cs.contracts],
                }
                for cs in self.codes
            ]
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'WasmContractStats':
        codes = []
        for item in d.get('codes', []):
            code_info = WasmCodeInfo.from_json(item['code_info'])
            contracts = [WasmContractEntry.from_dict(c) for c in item.get('contracts', [])]
            codes.append(WasmCodeStats(
                code_info=code_info,
                contracts=contracts,
                first_seen_ts=float(item.get('first_seen_ts', 0.0)),
            ))
        return cls(codes=codes)

    def __repr__(self) -> str:
        return (
            f"WasmContractStats("
            f"total_codes={self.total_codes}, "
            f"total_contracts={self.total_contracts})"
        )


# ---------------------------------------------------------------------------
# Infographic data models
# ---------------------------------------------------------------------------

@dataclass
class WasmDailyPoint:
    """Aggregated metrics for a single calendar day (for chart rendering)."""
    ts: float
    calls: int
    unique_users: int

    def to_dict(self) -> dict:
        return {'ts': self.ts, 'calls': self.calls, 'unique_users': self.unique_users}

    @classmethod
    def from_dict(cls, d: dict) -> 'WasmDailyPoint':
        return cls(ts=float(d['ts']), calls=int(d['calls']), unique_users=int(d['unique_users']))


@dataclass
class WasmTopContract:
    """One entry in the top-N contracts ranking."""
    address: str
    label: str
    calls: int
    unique_users: int
    display_label: str = ''

    def to_dict(self) -> dict:
        return {
            'address': self.address,
            'label': self.label,
            'display_label': self.display_label,
            'calls': self.calls,
            'unique_users': self.unique_users,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'WasmTopContract':
        return cls(
            address=str(d['address']),
            label=str(d.get('label', '')),
            display_label=str(d.get('display_label') or d.get('label', '')),
            calls=int(d['calls']),
            unique_users=int(d['unique_users']),
        )


@dataclass
class WasmPeriodStats:
    """
    Full stats snapshot for a rolling N-day window,
    ready for infographic generation.
    """
    days: float
    period_start_ts: float
    period_end_ts: float

    total_codes: int
    total_contracts: int

    new_codes: int
    new_contracts: int

    total_calls: int
    unique_users: int

    prev_total_calls: int
    prev_unique_users: int

    top_contracts: List[WasmTopContract]
    daily_chart: List[WasmDailyPoint]

    @property
    def calls_change_pct(self) -> Optional[float]:
        if not self.prev_total_calls:
            return None
        return (self.total_calls - self.prev_total_calls) / self.prev_total_calls * 100

    @property
    def users_change_pct(self) -> Optional[float]:
        if not self.prev_unique_users:
            return None
        return (self.unique_users - self.prev_unique_users) / self.prev_unique_users * 100

    def to_dict(self) -> dict:
        return {
            'days': self.days,
            'period_start_ts': self.period_start_ts,
            'period_end_ts': self.period_end_ts,
            'total_codes': self.total_codes,
            'total_contracts': self.total_contracts,
            'new_codes': self.new_codes,
            'new_contracts': self.new_contracts,
            'total_calls': self.total_calls,
            'unique_users': self.unique_users,
            'prev_total_calls': self.prev_total_calls,
            'prev_unique_users': self.prev_unique_users,
            # include computed diffs so renderer doesn't have to recalculate
            'calls_change_pct': self.calls_change_pct,
            'users_change_pct': self.users_change_pct,
            'top_contracts': [tc.to_dict() for tc in self.top_contracts],
            'daily_chart': [pt.to_dict() for pt in self.daily_chart],
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'WasmPeriodStats':
        return cls(
            days=float(d['days']),
            period_start_ts=float(d['period_start_ts']),
            period_end_ts=float(d['period_end_ts']),
            total_codes=int(d['total_codes']),
            total_contracts=int(d['total_contracts']),
            new_codes=int(d['new_codes']),
            new_contracts=int(d['new_contracts']),
            total_calls=int(d['total_calls']),
            unique_users=int(d['unique_users']),
            prev_total_calls=int(d['prev_total_calls']),
            prev_unique_users=int(d['prev_unique_users']),
            top_contracts=[WasmTopContract.from_dict(tc) for tc in d.get('top_contracts', [])],
            daily_chart=[WasmDailyPoint.from_dict(pt) for pt in d.get('daily_chart', [])],
        )

    def __repr__(self) -> str:
        return (
            f"WasmPeriodStats(days={self.days}, "
            f"codes={self.total_codes}(+{self.new_codes}), "
            f"contracts={self.total_contracts}(+{self.new_contracts}), "
            f"calls={self.total_calls}, users={self.unique_users})"
        )

