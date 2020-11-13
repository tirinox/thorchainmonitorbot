from dataclasses import dataclass


@dataclass
class RuneFairPrice:
    circulating: int = 500_000_000
    rune_vault_locked: int = 0
    real_rune_price: float = 0.0
    fair_price: float = 0.0
    tlv_usd: float = 0.0

    @property
    def market_cap(self):
        return self.real_rune_price * self.circulating


@dataclass
class PriceReport:
    current_price: float = 0.0
    price_1h: float = 0.0
    price_24h: float = 0.0
    price_7d: float = 0.0
    rank: int = 0
    fair_price: RuneFairPrice = RuneFairPrice()
