from typing import NamedTuple


class BEP2Transfer(NamedTuple):
    from_addr: str
    to_addr: str
    block: int
    tx_hash: str
    amount: float


class BEP2CEXFlow(NamedTuple):
    rune_cex_inflow: float
    rune_cex_outflow: float

    @property
    def rune_cex_netflow(self):
        return self.rune_cex_inflow - self.rune_cex_outflow
