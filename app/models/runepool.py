from typing import NamedTuple, Optional

from api.aionode.types import float_to_thor, ThorRunePool, ThorRunePoolPOL
from lib.constants import NATIVE_RUNE_SYMBOL, THOR_BASIS_POINT_MAX, thor_to_float
from .memo import ActionType, THORMemo
from .price import PriceHolder
from .tx import ThorAction, SUCCESS, ThorSubTx, ThorCoin


class AlertRunePoolAction(NamedTuple):
    tx_hash: str
    actor: str
    destination_address: str
    amount: float
    usd_amount: float
    is_deposit: bool
    height: int
    memo: THORMemo

    @property
    def is_withdrawal(self) -> bool:
        return not self.is_deposit

    @property
    def usd_per_rune(self) -> float:
        return self.usd_amount / self.amount

    @property
    def affiliate(self) -> str:
        return self.memo.affiliate_address

    @property
    def affiliate_rate(self) -> float:
        return self.memo.affiliate_fee_bp / THOR_BASIS_POINT_MAX

    @property
    def affiliate_usd(self) -> float:
        return self.usd_amount * self.affiliate_rate

    @property
    def as_thor_tx(self) -> ThorAction:
        in_tx_list, out_tx_list = [], []

        if self.is_deposit:
            in_tx_list.append(ThorSubTx(
                self.actor, [
                    ThorCoin(float_to_thor(self.amount), NATIVE_RUNE_SYMBOL)
                ],
                self.tx_hash,
                height=self.height,
            ))
            t = ActionType.RUNEPOOL_ADD
        else:
            out_tx_list.append(ThorSubTx(
                self.destination_address, [
                    ThorCoin(float_to_thor(self.amount), NATIVE_RUNE_SYMBOL)
                ],
                self.tx_hash,
                height=self.height,
            ))
            t = ActionType.RUNEPOOL_WITHDRAW

        return ThorAction(
            0, self.height, SUCCESS,
            type=str(t.value),
            pools=[],
            in_tx=in_tx_list, out_tx=out_tx_list,
            rune_amount=self.amount,
            full_volume_in_rune=self.amount,
            asset_per_rune=1.0,
        )


class POLState(NamedTuple):
    """The legacy POL of the Reserve (the one RUNEPool takes part in), not the ADR-024 pol_reserve module"""
    usd_per_rune: float
    value: ThorRunePoolPOL
    timestamp: int

    @property
    def rune_value(self):
        return thor_to_float(self.value.value)

    @property
    def usd_value(self):
        return self.usd_per_rune * self.rune_value


class RunepoolState(NamedTuple):
    pool: ThorRunePool
    n_providers: int
    avg_deposit: float
    usd_per_rune: float = 0.0
    timestamp: int = 0

    def to_dict(self):
        return {
            'pool': self.pool.to_dict(),
            'n_providers': self.n_providers,
            'avg_deposit': self.avg_deposit,
            'usd_per_rune': self.usd_per_rune,
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_json(cls, j):
        return cls(
            ThorRunePool.from_json(j.get('pool')),
            j.get('n_providers', 0),
            j.get('avg_deposit', 0.0),
            j.get('usd_per_rune', 0.0),
            j.get('timestamp', 0),
        )

    @property
    def rune_value(self):
        return thor_to_float(self.pool.providers.current_deposit) if self.pool else 0.0

    @property
    def usd_value(self):
        return self.usd_per_rune * self.rune_value

    @property
    def pnl(self):
        return thor_to_float(self.pool.providers.pnl) if self.pool else 0.0

    @property
    def providers_share(self):
        if self.pool and self.pool.pol.current_deposit:
            return self.pool.providers.current_deposit_float / self.pool.pol.current_deposit_float * 100.0
        else:
            return 0.0


class AlertPOLState(NamedTuple):
    current: POLState
    prices: Optional[PriceHolder] = None
    runepool: Optional[RunepoolState] = None


class AlertRunepoolStats(NamedTuple):
    current: RunepoolState
    previous: Optional[RunepoolState] = None
    usd_per_rune: float = 0.0
