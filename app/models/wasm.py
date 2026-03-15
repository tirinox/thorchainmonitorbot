from dataclasses import dataclass, field
from typing import List, Dict, Optional

from api.aionode.wasm import WasmCodeInfo


@dataclass
class WasmContractEntry:
    """A single contract instance with its on-chain label."""
    address: str
    label: str = ''

    def to_dict(self) -> dict:
        return {'address': self.address, 'label': self.label}

    @classmethod
    def from_dict(cls, d: dict) -> 'WasmContractEntry':
        return cls(address=d['address'], label=d.get('label', ''))


@dataclass
class WasmCodeStats:
    """Stats for a single deployed WASM code ID."""
    code_info: WasmCodeInfo
    contracts: List[WasmContractEntry] = field(default_factory=list)

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

    def get_code_stats(self, code_id: int) -> Optional['WasmCodeStats']:
        for c in self.codes:
            if c.code_id == code_id:
                return c
        return None

    @property
    def all_contracts(self) -> List['WasmContractEntry']:
        """Flat list of every contract entry across all code IDs."""
        return [entry for cs in self.codes for entry in cs.contracts]

    def find_label(self, address: str) -> Optional[str]:
        """Return label for a contract address from in-memory data, or None if not found."""
        for cs in self.codes:
            for entry in cs.contracts:
                if entry.address == address:
                    return entry.label
        return None

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
            codes.append(WasmCodeStats(code_info=code_info, contracts=contracts))
        return cls(codes=codes)

    def __repr__(self) -> str:
        return (
            f"WasmContractStats("
            f"total_codes={self.total_codes}, "
            f"total_contracts={self.total_contracts})"
        )
