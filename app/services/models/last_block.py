from dataclasses import dataclass


@dataclass
class LastBlock:
    chain: str
    last_observed_in: int
    last_signed_out: int
    thorchain: int
