from dataclasses import dataclass


@dataclass
class LastBlock:
    chain: str
    last_observed_in: int
    last_signed_out: int
    thorchain: int


class BlockProduceState:
    NormalPace = 'normal'
    TooFast = 'fast'
    TooSlow = 'slow'
    StateStuck = 'stuck'
    Producing = 'producing'


@dataclass
class EventBlockSpeed:
    state: str
    time_without_blocks: float
    block_speed: float
    points: list
