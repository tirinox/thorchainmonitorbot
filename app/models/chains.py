from dataclasses import dataclass, field
from typing import Dict

from api.aionode.types import ThorChainInfo


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
