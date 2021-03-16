from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, Iterable

from services.lib.constants import is_rune, THOR_DIVIDER_INV
from services.models.cap_info import BaseModelMixin


class ThorTxType:
    OLD_TYPE_STAKE = 'stake'  # deprecated (only for v1 parsing)
    TYPE_ADD_LIQUIDITY = 'addLiquidity'
    TYPE_SWAP = 'swap'
    OLD_TYPE_DOUBLE_SWAP = 'doubleSwap'  # deprecated (only for v1 parsing)
    TYPE_WITHDRAW = 'withdraw'
    OLD_TYPE_UNSTAKE = 'unstake'  # deprecated (only for v1 parsing)
    OLD_TYPE_ADD = 'add'
    TYPE_DONATE = 'donate'
    TYPE_REFUND = 'refund'


@dataclass
class ThorCoin:
    amount: str
    asset: str

    @property
    def amount_float(self):
        return int(self.amount) * THOR_DIVIDER_INV


@dataclass
class ThorSubTx:
    address: str
    coins: List[ThorCoin]
    tx_id: str

    @classmethod
    def parse(cls, j):
        coins = [ThorCoin(**cj) for cj in j.get('coins', [])]
        return cls(address=j.get('address', ''),
                   coins=coins,
                   tx_id=j.get('txID', ''))

    @property
    def first_asset(self):
        return self.coins[0].asset if self.coins else None

    @property
    def first_amount(self):
        return self.coins[0].amount if self.coins else None

    @classmethod
    def join_coins(cls, tx_list: Iterable):
        coin_dict = defaultdict(int)
        for tx in tx_list:
            for coin in tx.coins:
                coin_dict[coin.asset] += int(coin.amount)
        return cls(address='', coins=[ThorCoin(str(amount), asset) for asset, amount in coin_dict.items()], tx_id='')

    @property
    def rune_coin(self):
        return next((c for c in self.coins if is_rune(c.asset)), None)

    @property
    def none_rune_coins(self):
        return [c for c in self.coins if not is_rune(c.asset)]


@dataclass
class ThorMetaSwap:
    liquidity_fee: str
    network_fees: List[ThorCoin]
    trade_slip: str
    trade_target: str

    @classmethod
    def parse(cls, j):
        fees = [ThorCoin(**cj) for cj in j.get('networkFees', [])]
        return cls(liquidity_fee=j.get('liquidityFee', 0),
                   network_fees=fees,
                   trade_slip=j.get('tradeSlip', '0'),
                   trade_target=j.get('tradeTarget', '0'))


@dataclass
class ThorMetaWithdraw:
    asymmetry: str
    basis_points: str
    liquidity_units: str
    network_fees: List[ThorCoin]

    @classmethod
    def parse(cls, j):
        fees = [ThorCoin(**cj) for cj in j.get('networkFees', [])]
        return cls(asymmetry=j.get('asymmetry', '0'),
                   network_fees=fees,
                   liquidity_units=j.get('liquidityUnits', '0'),
                   basis_points=j.get('basisPoints', '0'))


@dataclass
class ThorMetaRefund:
    reason: str
    network_fees: List[ThorCoin]

    @classmethod
    def parse(cls, j):
        fees = [ThorCoin(**cj) for cj in j.get('networkFees', [])]
        return cls(reason=j.get('reason', '?'),
                   network_fees=fees)


@dataclass
class ThorMetaAddLiquidity:
    liquidity_units: str

    @classmethod
    def parse(cls, j):
        return cls(liquidity_units=j.get('liquidityUnits', '0'))


@dataclass
class ThorTx:
    date: str
    height: str
    status: str
    type: str
    pools: List[str]
    in_tx: List[ThorSubTx]
    out_tx: List[ThorSubTx]
    meta_add: Optional[ThorMetaAddLiquidity] = None
    meta_withdraw: Optional[ThorMetaWithdraw] = None
    meta_swap: Optional[ThorMetaSwap] = None
    meta_refund: Optional[ThorMetaRefund] = None

    SUCCESS = 'success'
    PENDING = 'pending'

    @property
    def is_success(self):
        return self.status == self.SUCCESS

    @property
    def date_timestamp(self):
        return int(self.date) * 1e-10

    @property
    def height_int(self):
        return int(self.height)

    @property
    def tx_hash(self):
        if self.in_tx:
            return self.in_tx[0].tx_id
        elif self.out_tx:
            return self.out_tx[0].tx_id
        else:
            return self.date

    def sum_of_asset(self, asset, in_only=False, out_only=False):
        search_realm = self.in_tx if in_only else self.out_tx if out_only else in_only + out_only
        return sum(coin.amount_float for sub_tx in search_realm for coin in sub_tx.coins if coin.asset == asset)

    def sum_of_rune(self, in_only=False, out_only=False):
        search_realm = self.in_tx if in_only else self.out_tx if out_only else in_only + out_only
        return sum(coin.amount_float for sub_tx in search_realm for coin in sub_tx.coins if is_rune(coin.asset))


@dataclass
class StakeTx(BaseModelMixin):
    date: int
    type: str
    pool: str
    address: str
    asset_amount: float
    rune_amount: float
    hash: str
    full_rune: float
    asset_per_rune: float
    tx: ThorTx

    @classmethod
    def load_from_thor_tx(cls, tx: ThorTx):
        t = tx.type
        if t not in (ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_ADD_LIQUIDITY):
            return None

        pool = tx.pools[0]

        if t == ThorTxType.TYPE_ADD_LIQUIDITY:
            rune_amount = tx.sum_of_rune(in_only=True)
            asset_amount = tx.sum_of_asset(pool, in_only=True)
        elif t == ThorTxType.TYPE_WITHDRAW:
            rune_amount = tx.sum_of_rune(out_only=True)
            asset_amount = tx.sum_of_asset(pool, out_only=True)
        else:
            return None

        return cls(date=int(tx.date_timestamp),
                   type=t,
                   pool=pool,
                   address=tx.in_tx[0].address,
                   asset_amount=asset_amount,
                   rune_amount=rune_amount,
                   hash=tx.tx_hash,
                   full_rune=0.0,
                   asset_per_rune=0.0,
                   tx=tx)

    def asymmetry(self, force_abs=False):
        rune_asset_amount = self.asset_amount * self.asset_per_rune
        factor = (self.rune_amount / (rune_asset_amount + self.rune_amount) - 0.5) * 200.0  # -100 % ... + 100 %
        return abs(factor) if force_abs else factor

    def symmetry_rune_vs_asset(self):
        f = 100.0 / self.full_rune
        return self.rune_amount * f, self.asset_amount / self.asset_per_rune * f

    @classmethod
    def collect_pools(cls, txs):
        return set(t.pool for t in txs)

    def calc_full_rune_amount(self, asset_per_rune):
        self.asset_per_rune = asset_per_rune
        self.full_rune = self.asset_amount / asset_per_rune + self.rune_amount
        return self.full_rune
