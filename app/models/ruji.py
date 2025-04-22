from typing import NamedTuple, Dict, Optional, List

from api.aionode.wasm import WasmContract
from lib.date_utils import now_ts
from models.asset import Asset


class EventRujiMerge(NamedTuple):
    tx_id: str
    height: int
    from_address: str
    volume_usd: float
    amount: float
    asset: str
    rate: float
    decay_factor: float
    timestamp: int

    @classmethod
    def from_dict(cls, d):
        return cls(
            tx_id=d['tx_id'],
            height=int(d['height']),
            from_address=d['from_address'],
            volume_usd=float(d['volume_usd']),
            amount=float(d['amount']),
            asset=d['asset'],
            rate=float(d['rate']),
            decay_factor=float(d['decay_factor']),
            timestamp=int(d.get('timestamp', 0)),
        )

    def to_dict(self):
        return self._asdict()


def ruji_parse_timestamp(timestamp: str) -> float:
    return float(timestamp) / 1e9


class MergeConfig(NamedTuple):
    merge_denom: str
    merge_supply: int
    ruji_denom: str
    ruji_allocation: int
    decay_starts_at: float  # timestamp
    decay_ends_at: float  # timestamp

    @classmethod
    def from_dict(cls, data):
        data = data['data'] if 'data' in data else data
        return cls(
            merge_denom=data['merge_denom'],
            merge_supply=int(data['merge_supply']),
            ruji_denom=data['ruji_denom'],
            ruji_allocation=int(data['ruji_allocation']),
            decay_starts_at=ruji_parse_timestamp(data['decay_starts_at']),
            decay_ends_at=ruji_parse_timestamp(data['decay_ends_at']),
        )

    def decay_factor(self, now: float) -> float:
        if now <= self.decay_starts_at:
            return 1.0
        if now > self.decay_ends_at:
            return 0.0
        remaining = float(self.decay_ends_at) - float(now)
        duration = float(self.decay_ends_at) - float(self.decay_starts_at)
        return remaining / duration

    def merge_ratio(self, now: float) -> float:
        factor = self.decay_factor(now)
        return self.max_rate * factor

    @property
    def max_rate(self):
        return float(self.ruji_allocation) / float(self.merge_supply)

    def calculate_decay(self, amount_in, amount_out):
        # Calculate the decay factor based on the amount_in and amount_out
        if amount_in <= 0 or amount_out <= 0:
            return 0.0

        rate = float(amount_out) / float(amount_in)
        decay_factor = rate / self.max_rate
        return decay_factor


class MergeStatus(NamedTuple):
    merged: int
    shares: int
    size: int

    @classmethod
    def from_dict(cls, data):
        data = data['data'] if 'data' in data else data
        return cls(
            merged=int(data['merged']),
            shares=int(data['shares']),
            size=int(data['size']),
        )


class MergeContract(WasmContract):
    def __init__(self, thor_connector, contract_address):
        super().__init__(thor_connector, contract_address)
        self.config: Optional[MergeConfig] = None
        self.status: Optional[MergeStatus] = None
        self.price_usd = 0.0

    async def load_config(self):
        data = await self.query_contract({"config": {}})
        self.config = MergeConfig.from_dict(data)
        return self.config

    async def load_status(self):
        data = await self.query_contract({"status": {}})
        self.status = MergeStatus.from_dict(data)
        return self.status

    def set_price(self, price: float):
        self.price_usd = price

    def __repr__(self):
        return (
            f'MergeContract({self.contract_address}, 1 = {self.config.merge_denom} = ${self.price_usd:.4f},'
            f'1 RUJI = ${self.price_usd_per_ruji:.4f})'
        )

    @property
    def price_usd_per_ruji(self):
        merge_ratio = float(self.config.merge_ratio(now_ts()))
        # 1 [denom] -> merge_ratio RUJI
        return self.price_usd / merge_ratio

    def to_dict(self):
        return {
            "contract_address": self.contract_address,
            "config": self.config if self.config else None,
            "status": self.status if self.status else None,
            "price_usd": self.price_usd
        }


class MergeSystem(NamedTuple):
    contracts: List[MergeContract]

    RUJI_MERGE_CONTRACTS = [
        "thor14hj2tavq8fpesdwxxcu44rty3hh90vhujrvcmstl4zr3txmfvw9s3p2nzy",
        "thor1yyca08xqdgvjz0psg56z67ejh9xms6l436u8y58m82npdqqhmmtqrsjrgh",
        "thor1suhgf5svhu4usrurvxzlgn54ksxmn8gljarjtxqnapv8kjnp4nrsw5xx2d",
        "thor1yw4xvtc43me9scqfr2jr2gzvcxd3a9y4eq7gaukreugw2yd2f8tsz3392y",
        "thor1cnuw3f076wgdyahssdkd0g3nr96ckq8cwa2mh029fn5mgf2fmcmsmam5ck",
        "thor1ltd0maxmte3xf4zshta9j5djrq9cl692ctsp9u5q0p9wss0f5lms7us4yf"
    ]

    def find_contract_by_denom(self, denom: str):
        denom = denom.lower()
        return next((
            contract for _, contract in self.contracts
            if contract.config.merge_denom.lower() == denom
        ), None)

    @property
    def all_denoms(self):
        return set(cfg.config.merge_denom for cfg in self.contracts)

    def set_prices(self, prices):
        for contract in self.contracts:
            ticker = Asset.from_string(contract.config.merge_denom)
            price = prices.get(ticker.name)
            contract.set_price(price)


class AlertRujiraMergeStats(NamedTuple):
    merge: MergeSystem
    top_txs: List[EventRujiMerge]