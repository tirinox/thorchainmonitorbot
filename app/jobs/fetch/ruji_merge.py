from decimal import Decimal
from typing import NamedTuple, Dict, Optional

from api.aionode.wasm import WasmContract
from lib.date_utils import now_ts
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import a_result_cached
from models.asset import Asset


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

    def decay_factor(self, now: float) -> Decimal:
        if now <= self.decay_starts_at:
            return Decimal('1')
        if now > self.decay_ends_at:
            return Decimal('0')
        remaining = Decimal(self.decay_ends_at) - Decimal(now)
        duration = Decimal(self.decay_ends_at) - Decimal(self.decay_starts_at)
        return remaining / duration

    def merge_ratio(self, now: float) -> Decimal:
        factor = self.decay_factor(now)
        return (Decimal(self.ruji_allocation) / Decimal(self.merge_supply)) * factor


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
        # 1 denom -> merge_ratio RUJI
        return self.price_usd / merge_ratio


class MergeSystem(NamedTuple):
    contracts: Dict[str, MergeContract]

    RUJI_MERGE_CONTRACTS = [
        "thor1yyca08xqdgvjz0psg56z67ejh9xms6l436u8y58m82npdqqhmmtqrsjrgh",
        "thor1yw4xvtc43me9scqfr2jr2gzvcxd3a9y4eq7gaukreugw2yd2f8tsz3392y",
        "thor1suhgf5svhu4usrurvxzlgn54ksxmn8gljarjtxqnapv8kjnp4nrsw5xx2d",
        "thor14hj2tavq8fpesdwxxcu44rty3hh90vhujrvcmstl4zr3txmfvw9s3p2nzy",
        "thor1cnuw3f076wgdyahssdkd0g3nr96ckq8cwa2mh029fn5mgf2fmcmsmam5ck",
        "thor1ltd0maxmte3xf4zshta9j5djrq9cl692ctsp9u5q0p9wss0f5lms7us4yf"
    ]

    def find_contract_by_denom(self, denom: str):
        denom = denom.lower()
        return next((
            contract for address, contract in self.contracts.items()
            if contract.config.merge_denom.lower() == denom
        ), None)

    @property
    def all_denoms(self):
        return set(cfg.config.merge_denom for cfg in self.contracts.values())

    def set_prices(self, prices):
        for contract in self.contracts.values():
            ticker = Asset.from_string(contract.config.merge_denom)
            price = prices.get(ticker.name)
            contract.set_price(price)


class RujiMergeStatsFetcher(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.system = MergeSystem({
            address: MergeContract(deps.thor_connector, address)
            for address in MergeSystem.RUJI_MERGE_CONTRACTS
        })

    async def fetch(self):
        for contract in self.system.contracts.values():
            await contract.load_config()
            await contract.load_status()

        prices = await self.get_prices_usd_from_gecko()
        self.system.set_prices(prices)

        return self.system

    @a_result_cached(ttl=120.0)
    async def get_prices_usd_from_gecko(self):
        url = "https://api.coingecko.com/api/v3/simple/price"
        coin_ids = {
            "LVN": "levana-protocol",
            "KUJI": "kujira",
            "FUZN": "fuzion",
            "WINK": "winkhub",
            "NSTK": "unstake"
        }
        params = {
            "ids": ",".join(coin_ids.values()),
            "vs_currencies": "usd"
        }

        async with self.deps.session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                prices = {coin: data.get(coin_ids[coin], {}).get("usd") for coin in coin_ids}

                # Check for missing prices and set defaults
                if not prices.get("NSTK"):
                    self.logger.warning(f"No NSTK price. Using last known hardcoded value")
                    prices["NSTK"] = 0.01253
                prices["RKUJI"] = prices["KUJI"]

                return prices
            else:
                raise Exception(f"Failed to fetch data. Status code: {response.status}")
