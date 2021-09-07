from typing import NamedTuple, List

from services.lib.constants import thor_to_float


class ThorMonChainHeight(NamedTuple):
    chain: str
    height: int

    @classmethod
    def from_json(cls, j):
        return cls(chain=j.get('chain', ''), height=int(j.get('height', 0)))


def is_ok(j, key):
    return str(j.get(key, 'BAD')) == 'OK'


class ThorMonNode(NamedTuple):
    node_address: str
    ip_address: str
    bond: float
    current_award: float
    slash_points: int
    version: str
    status: str
    observe_chains: List[ThorMonChainHeight]
    requested_to_leave: bool
    forced_to_leave: bool
    leave_height: int
    status_since: int
    thor: bool
    rpc: bool
    midgard: bool
    bifrost: bool

    original_dict: dict  # holds unparsed data

    @classmethod
    def from_json(cls, j):
        raw_chains = j.get('observe_chains') or []
        chains = [ThorMonChainHeight.from_json(o) for o in raw_chains]
        return cls(
            node_address=j.get('node_address', ''),
            ip_address=j.get('ip_address', ''),
            bond=thor_to_float(j.get('bond', 0)),
            current_award=thor_to_float(j.get('current_award', 0)),
            slash_points=int(j.get('slash_points', 0)),
            version=j.get('version', '0.0.0'),
            status=j.get('status', 'Standby'),
            observe_chains=chains,
            requested_to_leave=bool(j.get('requested_to_leave')),
            forced_to_leave=bool(j.get('forced_to_leave')),
            leave_height=int(j.get('leave_height', 0)),
            status_since=int(j.get('status_since', 0)),
            thor=is_ok(j, 'thor'),
            rpc=is_ok(j, 'rpc'),
            midgard=is_ok(j, 'midgard'),
            bifrost=is_ok(j, 'bifrost'),

            original_dict=j
        )


class ThorMonAnswer(NamedTuple):
    last_block: int
    next_churn: int
    nodes: List[ThorMonNode]


    @classmethod
    def empty(cls):
        return ThorMonAnswer(0, 0, [])

    @classmethod
    def from_json(cls, j):
        return cls(
            last_block=int(j.get('lastblock', 0)),
            next_churn=int(j.get('next_churn', 0)),
            nodes=[ThorMonNode.from_json(node) for node in j.get('nodes', [])]
        )