from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, Iterable

from services.lib.constants import is_rune, THOR_DIVIDER_INV, RUNE_SYMBOL, Chains, NATIVE_RUNE_SYMBOL
from services.lib.money import Asset
from services.models.pool_info import PoolInfo


class ThorTxType:
    OLD_TYPE_STAKE = 'stake'  # deprecated (only for v1 parsing)
    TYPE_ADD_LIQUIDITY = 'addLiquidity'

    TYPE_SWAP = 'swap'
    OLD_TYPE_DOUBLE_SWAP = 'doubleSwap'  # deprecated (only for v1 parsing)

    TYPE_WITHDRAW = 'withdraw'

    OLD_TYPE_UNSTAKE = 'unstake'  # deprecated (only for v1 parsing)
    OLD_TYPE_ADD = 'add'  # deprecated (only for v1 parsing)

    TYPE_DONATE = 'donate'

    TYPE_REFUND = 'refund'
    TYPE_SWITCH = 'switch'  # BNB/ETH Rune => Native RUNE


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

    @property
    def basis_points_int(self):
        return int(self.basis_points)

    @property
    def liquidity_units_int(self):
        return int(self.liquidity_units)

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

    @property
    def liquidity_units_int(self):
        return int(self.liquidity_units)

    @classmethod
    def parse(cls, j):
        return cls(liquidity_units=j.get('liquidityUnits', '0'))


SUCCESS = 'success'
PENDING = 'pending'


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

    @property
    def is_success(self):
        return self.status == SUCCESS

    @property
    def date_timestamp(self):
        return int(int(self.date) * 1e-9)

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

    @property
    def first_input_tx_hash(self):
        return self.in_tx[0].tx_id if self.in_tx else None

    @property
    def first_output_tx_hash(self):
        return self.out_tx[0].tx_id if self.out_tx else None

    @property
    def first_input_tx(self):
        return self.in_tx[0] if self.in_tx else None

    @property
    def first_output_tx(self):
        return self.in_tx[0] if self.in_tx else None

    @property
    def input_thor_address(self) -> Optional[str]:
        for in_tx in self.in_tx:
            if Chains.detect_chain(in_tx.address) == Chains.THOR:
                return in_tx.address

    @property
    def is_asset_side_only(self):
        return self.input_thor_address is None

    @property
    def sender_address(self):
        return self.in_tx[0].address if self.in_tx else None

    @property
    def rune_input_address(self):
        for tx in self.in_tx:
            for coin in tx.coins:
                if coin.asset == NATIVE_RUNE_SYMBOL:
                    return tx.address

    @property
    def sender_address_and_chain(self):
        rune_address = self.rune_input_address
        if rune_address:
            return rune_address, Chains.THOR
        elif self.in_tx:
            first_tx = self.first_input_tx
            for coin in first_tx.coins:
                chain = Asset(coin.asset).chain
                return first_tx.address, chain
        else:
            return None, None

    def search_realm(self, in_only=False, out_only=False):
        return self.in_tx if in_only else self.out_tx if out_only else in_only + out_only

    def get_sub_tx(self, asset, in_only=False, out_only=False):
        for sub_tx in self.search_realm(in_only, out_only):
            for coin in sub_tx.coins:
                if asset == coin.asset:
                    return sub_tx
                elif is_rune(asset) and is_rune(coin.asset):
                    return sub_tx

    def sum_of(self, predicate, in_only=False, out_only=False):
        return sum(coin.amount_float for sub_tx in self.search_realm(in_only, out_only) for coin in sub_tx.coins
                   if predicate(coin))

    def sum_of_asset(self, asset, in_only=False, out_only=False):
        return self.sum_of(lambda c: c.asset == asset, in_only, out_only)

    def sum_of_non_rune(self, in_only=False, out_only=False):
        return self.sum_of(lambda c: not is_rune(c.asset), in_only, out_only)

    def sum_of_rune(self, in_only=False, out_only=False):
        return self.sum_of(lambda c: is_rune(c.asset), in_only, out_only)

    def not_rune_asset(self, in_only=False, out_only=False):
        for sub_tx in self.search_realm(in_only, out_only):
            for coin in sub_tx.coins:
                if not is_rune(coin):
                    return coin

    @property
    def first_pool(self):
        return self.pools[0] if self.pools else None

    def __hash__(self) -> int:
        return int(self.tx_hash, 16)

    def __eq__(self, other):
        if isinstance(other, ThorTx):
            return self.height_int == other.height_int and self.tx_hash == other.tx_hash and self.type == other.type
        else:
            return False


def final_liquidity(txs: List[ThorTx]):
    lp = 0
    for tx in txs:
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            lp += tx.meta_add.liquidity_units_int
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            lp += tx.meta_withdraw.liquidity_units_int
    return lp


def cut_txs_before_previous_full_withdraw(txs: List[ThorTx]):
    lp = 0
    new_txs = []
    for tx in txs:
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            lp += tx.meta_add.liquidity_units_int
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            lp += tx.meta_withdraw.liquidity_units_int

        new_txs.append(tx)

        if lp <= 0:
            # oops! user has withdrawn all funds completely: resetting the accumulator!
            new_txs = []
    return new_txs


@dataclass
class ThorTxExtended(ThorTx):
    # for add, withdraw, donate
    address_rune: str = ''
    address_asset: str = ''
    tx_hash_rune: str = ''
    tx_hash_asset: str = ''
    asset_amount: float = 0.0
    rune_amount: float = 0.0

    # for switch, refund, swap
    # input_address: str = ''
    # output_address: str = ''
    # input_tx_hash: str = ''
    # output_tx_hash: str = ''
    # input_amount: float = 0.0
    # output_amount: float = 0.0
    # input_asset: str = ''
    # output_asset: str = ''

    # filled by "calc_full_rune_amount"
    full_rune: float = 0.0  # TX volume
    asset_per_rune: float = 0.0

    @classmethod
    def load_from_thor_tx(cls, tx: ThorTx):
        return cls(**tx.__dict__)

    def __post_init__(self):
        t = self.type
        if t == ThorTxType.TYPE_ADD_LIQUIDITY or t == ThorTxType.TYPE_DONATE:
            pool = self.first_pool
            self.rune_amount = self.sum_of_rune(in_only=True)
            self.asset_amount = self.sum_of_asset(pool, in_only=True)

            rune_sub_tx = self.get_sub_tx(RUNE_SYMBOL, in_only=True)
            self.address_rune = rune_sub_tx.address if rune_sub_tx else None
            self.tx_hash_rune = rune_sub_tx.tx_id if rune_sub_tx else None

            asset_sub_tx = self.get_sub_tx(pool, in_only=True)
            self.address_asset = asset_sub_tx.address if asset_sub_tx else None
            self.tx_hash_asset = asset_sub_tx.tx_id if asset_sub_tx else None

        elif t == ThorTxType.TYPE_WITHDRAW:
            pool = self.first_pool
            self.rune_amount = self.sum_of_rune(out_only=True)
            self.asset_amount = self.sum_of_asset(pool, out_only=True)

            sub_tx_rune = self.get_sub_tx(RUNE_SYMBOL, in_only=True)
            self.address_rune = sub_tx_rune.address if sub_tx_rune else self.in_tx[0].address

            self.tx_hash_rune = self.get_sub_tx(RUNE_SYMBOL, out_only=True)
            self.tx_hash_asset = self.get_sub_tx(pool, out_only=True)

        elif t in (ThorTxType.TYPE_SWITCH, ThorTxType.TYPE_REFUND, ThorTxType.TYPE_SWAP):
            # only outputs
            self.rune_amount = self.sum_of_rune(out_only=True)
            self.asset_amount = self.sum_of_non_rune(out_only=True)

    def asymmetry(self, force_abs=False):
        rune_asset_amount = self.asset_amount * self.asset_per_rune
        factor = (self.rune_amount / (rune_asset_amount + self.rune_amount) - 0.5) * 200.0  # -100 % ... + 100 %
        return abs(factor) if force_abs else factor

    def symmetry_rune_vs_asset(self):
        if not self.full_rune:
            return 0.0, 0.0

        f = 100.0 / self.full_rune
        return self.rune_amount * f, self.asset_amount / self.asset_per_rune * f

    def calc_full_rune_amount(self, asset_per_rune):
        self.asset_per_rune = asset_per_rune
        if asset_per_rune == 0.0:
            self.full_rune = self.rune_amount
        else:
            self.full_rune = self.asset_amount / asset_per_rune + self.rune_amount
        return self.full_rune

    def get_usd_volume(self, usd_per_rune):
        return usd_per_rune * self.full_rune

    def what_percent_of_pool(self, pool_info: PoolInfo) -> float:
        percent_of_pool = 100.0
        if pool_info:
            correction = self.full_rune if self.type == ThorTxType.TYPE_WITHDRAW else 0.0
            percent_of_pool = pool_info.percent_share(self.full_rune, correction)
        return percent_of_pool
