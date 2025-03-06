from dataclasses import dataclass, field
from typing import Dict

from api.aionode.types import ThorChainInfo


@dataclass
class ChainInfoHolder:
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
            (chain, info.is_perfect)
            for chain, info in self.state_dict.items()
        ]
