import dataclasses
from typing import NamedTuple, Optional

from pydantic.fields import List

from aionode.types import float_to_thor, ThorRunePool, ThorRunePoolPOL
from services.lib.constants import NATIVE_RUNE_SYMBOL, THOR_BASIS_POINT_MAX, thor_to_float
from services.models.memo import ActionType, THORMemo
from services.models.pool_member import PoolMemberDetails
from services.models.price import LastPriceHolder
from services.models.tx import ThorTx, SUCCESS, ThorSubTx, ThorCoin


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
    def as_thor_tx(self) -> ThorTx:
        in_tx_list, out_tx_list = [], []

        if self.is_deposit:
            in_tx_list.append(ThorSubTx(
                self.actor, [
                    ThorCoin(float_to_thor(self.amount), NATIVE_RUNE_SYMBOL)
                ],
                self.tx_hash
            ))
            t = ActionType.RUNEPOOL_ADD
        else:
            out_tx_list.append(ThorSubTx(
                self.destination_address, [
                    ThorCoin(float_to_thor(self.amount), NATIVE_RUNE_SYMBOL)
                ],
                self.tx_hash
            ))
            t = ActionType.RUNEPOOL_WITHDRAW

        return ThorTx(
            0, self.height, SUCCESS,
            type=t.value,
            pools=[],
            in_tx=in_tx_list, out_tx=out_tx_list,
            tx_hash_rune=self.tx_hash,
            rune_amount=self.amount,
            full_rune=self.amount,
            asset_per_rune=1.0,
        )


class POLState(NamedTuple):
    usd_per_rune: float
    value: ThorRunePoolPOL

    @property
    def is_zero(self):
        if not self.value:
            return True

        return (not self.value.value or self.rune_value == 0) and \
            (self.rune_deposited == 0 and self.rune_withdrawn == 0)

    @property
    def rune_value(self):
        return thor_to_float(self.value.value)

    @property
    def rune_deposited(self):
        return thor_to_float(self.value.rune_deposited)

    @property
    def rune_withdrawn(self):
        return thor_to_float(self.value.rune_withdrawn)

    @property
    def usd_value(self):
        return self.usd_per_rune * self.rune_value

    def pol_utilization_percent(self, mimir_max_deposit):
        return self.rune_value / mimir_max_deposit * 100.0 if mimir_max_deposit else 0.0

    @property
    def pnl_percent(self):
        return self.value.pnl / self.value.current_deposit if self.value.current_deposit else 0.0


class AlertPOLState(NamedTuple):
    current: POLState
    membership: List[PoolMemberDetails]
    previous: Optional[POLState] = None
    prices: Optional[LastPriceHolder] = None
    runepool: Optional[ThorRunePool] = None
    mimir_synth_target_ptc: float = 45.0  # %
    mimir_max_deposit: float = 10_000.0  # Rune

    @property
    def pol_utilization(self):
        return self.current.pol_utilization_percent(self.mimir_max_deposit)

    @classmethod
    def load_from_series(cls, j):
        usd_per_rune = float(j.get('usd_per_rune', 1.0))
        pol = POLState(usd_per_rune, ThorRunePoolPOL(**j.get('pol')))
        membership = [PoolMemberDetails(**it) for it in j.get('membership', [])]
        return cls(
            current=pol,
            membership=membership,
        )

    @property
    def to_json_for_series(self):
        return {
            'pol': self.current.value._asdict(),
            'membership': [
                dataclasses.asdict(m) for m in self.membership
            ],
            'usd_per_rune': self.current.usd_per_rune,
        }


class AlertRunepoolStats(NamedTuple):
    current: ThorRunePool
    previous: Optional[ThorRunePool] = None
