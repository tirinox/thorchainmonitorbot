from dataclasses import dataclass, field
from typing import List, Dict

from api.aionode.wasm import WasmCodeInfo


@dataclass
class WasmCodeStats:
    """Stats for a single deployed WASM code ID."""
    code_info: WasmCodeInfo
    contract_count: int = 0

    @property
    def code_id(self) -> int:
        return self.code_info.code_id

    @property
    def creator(self) -> str:
        return self.code_info.creator

    @property
    def data_hash(self) -> str:
        return self.code_info.data_hash


@dataclass
class WasmContractStats:
    """
    Aggregated snapshot of all WASM code variants and their contract instances.
    Returned by WasmCache and refreshed every hour.
    """
    codes: List[WasmCodeStats] = field(default_factory=list)

    @property
    def total_codes(self) -> int:
        """Number of distinct code variants deployed on-chain."""
        return len(self.codes)

    @property
    def total_contracts(self) -> int:
        """Total number of contract instances across all code IDs."""
        return sum(c.contract_count for c in self.codes)

    @property
    def contracts_per_code(self) -> Dict[int, int]:
        """Mapping of code_id → contract_count."""
        return {c.code_id: c.contract_count for c in self.codes}

    def get_code_stats(self, code_id: int) -> WasmCodeStats | None:
        for c in self.codes:
            if c.code_id == code_id:
                return c
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
                    'contract_count': cs.contract_count,
                }
                for cs in self.codes
            ]
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'WasmContractStats':
        codes = []
        for item in d.get('codes', []):
            code_info = WasmCodeInfo.from_json(item['code_info'])
            codes.append(WasmCodeStats(code_info=code_info, contract_count=item['contract_count']))
        return cls(codes=codes)

    def __repr__(self) -> str:
        return (
            f"WasmContractStats("
            f"total_codes={self.total_codes}, "
            f"total_contracts={self.total_contracts})"
        )

