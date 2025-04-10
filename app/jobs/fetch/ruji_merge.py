from decimal import Decimal
from typing import NamedTuple, Dict

from api.aionode.wasm import WasmContract
from lib.depcont import DepContainer
from lib.logs import WithLogger


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
    async def config(self):
        data = await self.query_contract({"config": {}})
        return MergeConfig.from_dict(data)

    async def status(self):
        data = await self.query_contract({"status": {}})
        return MergeStatus.from_dict(data)


class MergeSystem(NamedTuple):
    configs: Dict[str, MergeConfig]
    statuses: Dict[str, MergeStatus]

    RUJI_MERGE_CONTRACTS = [
        "thor1yyca08xqdgvjz0psg56z67ejh9xms6l436u8y58m82npdqqhmmtqrsjrgh",
        "thor1yw4xvtc43me9scqfr2jr2gzvcxd3a9y4eq7gaukreugw2yd2f8tsz3392y",
        "thor1suhgf5svhu4usrurvxzlgn54ksxmn8gljarjtxqnapv8kjnp4nrsw5xx2d",
        "thor14hj2tavq8fpesdwxxcu44rty3hh90vhujrvcmstl4zr3txmfvw9s3p2nzy",
        "thor1cnuw3f076wgdyahssdkd0g3nr96ckq8cwa2mh029fn5mgf2fmcmsmam5ck",
        "thor1ltd0maxmte3xf4zshta9j5djrq9cl692ctsp9u5q0p9wss0f5lms7us4yf"
    ]

    def find_config_and_status_by_denom(self, denom: str):
        denom = denom.lower()
        return next((
            (self.configs[contract], self.statuses[contract]) for contract, config in self.configs.items()
            if config.merge_denom.lower() == denom
        ), None)

    @property
    def all_denoms(self):
        return set(cfg.merge_denom for cfg in self.configs.values())


class RujiMergeStatsFetcher(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.contracts = [
            MergeContract(deps.thor_connector, contract)
            for contract in MergeSystem.RUJI_MERGE_CONTRACTS
        ]

    async def fetch(self):
        configs = {}
        statuses = {}
        for contract in self.contracts:
            config = await contract.config()
            status = await contract.status()
            self.logger.info(f"Config: {config}")
            self.logger.info(f"Status: {status}")
            configs[contract.contract_address] = config
            statuses[contract.contract_address] = status

        return MergeSystem(configs, statuses)
