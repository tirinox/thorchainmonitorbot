from typing import NamedTuple


class BEP2Transfer(NamedTuple):
    from_addr: str
    to_addr: str
    block: int
    tx_hash: str
    amount: float