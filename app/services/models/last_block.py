from dataclasses import dataclass


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
