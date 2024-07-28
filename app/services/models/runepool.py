from typing import NamedTuple

from aionode.types import float_to_thor
from services.lib.constants import NATIVE_RUNE_SYMBOL, THOR_BASIS_POINT_MAX
from services.models.memo import ActionType, THORMemo
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
