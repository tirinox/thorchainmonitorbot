from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, Iterable, NamedTuple, Tuple

from services.lib.constants import is_rune, RUNE_SYMBOL, Chains, thor_to_float, THOR_BASIS_POINT_MAX
from services.lib.date_utils import now_ts
from services.lib.money import Asset
from services.lib.texts import sum_and_str
from services.lib.w3.token_record import SwapInOut
from services.models.cap_info import ThorCapInfo
from services.models.lp_info import LPAddress
from services.models.mimir import MimirHolder
from services.models.pool_info import PoolInfo, PoolInfoMap


class ThorTxType:
    TYPE_ADD_LIQUIDITY = 'addLiquidity'
    TYPE_SWAP = 'swap'
    TYPE_WITHDRAW = 'withdraw'
    TYPE_DONATE = 'donate'
    TYPE_REFUND = 'refund'
    TYPE_SWITCH = 'switch'  # BNB/ETH Rune => Native RUNE


class ThorCoin(NamedTuple):
    amount: str = '0'
    asset: str = ''

    @property
    def amount_float(self):
        return thor_to_float(self.amount)

    @staticmethod
    def merge_two(a: 'ThorCoin', b: 'ThorCoin'):
        assert a.asset == b.asset
        return ThorCoin(sum_and_str(a.amount, b.amount), a.asset)


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
    affiliate_fee: float = 0.0  # (0..1) range
    memo: str = ''

    # todo: add aff address

    @classmethod
    def parse(cls, j):
        fees = [ThorCoin(**cj) for cj in j.get('networkFees', [])]
        return cls(liquidity_fee=j.get('liquidityFee', 0),
                   network_fees=fees,
                   trade_slip=j.get('swapSlip', '0'),
                   trade_target=j.get('swapTarget', '0'),
                   affiliate_fee=float(j.get('affiliateFee', 0)) / THOR_BASIS_POINT_MAX,
                   memo=j.get('memo', ''))

    @property
    def trade_slip_percent(self):
        return int(self.trade_slip) / 100.0

    @property
    def liquidity_fee_rune_float(self):
        return thor_to_float(self.liquidity_fee)

    @staticmethod
    def merge_two(a: 'ThorMetaSwap', b: 'ThorMetaSwap'):
        if a and b:
            return ThorMetaSwap(
                liquidity_fee=sum_and_str(a.liquidity_fee, b.liquidity_fee),
                network_fees=a.network_fees + b.network_fees,
                trade_slip=sum_and_str(a.trade_slip, b.trade_slip),
                trade_target=sum_and_str(a.trade_target, b.trade_target),
                affiliate_fee=max(a.affiliate_fee, b.affiliate_fee),
                memo=a.memo if a.memo else b.memo,
            )
        else:
            return a or b


@dataclass
class ThorMetaWithdraw:
    asymmetry: str
    basis_points: str
    liquidity_units: str
    network_fees: List[ThorCoin]
    impermanent_loss_protection: str

    @property
    def basis_points_int(self):
        return int(self.basis_points)

    @property
    def liquidity_units_int(self):
        return int(self.liquidity_units)

    @property
    def ilp_rune(self):
        return thor_to_float(self.impermanent_loss_protection)

    @classmethod
    def parse(cls, j):
        fees = [ThorCoin(**cj) for cj in j.get('networkFees', [])]
        return cls(
            asymmetry=j.get('asymmetry', '0'),
            network_fees=fees,
            liquidity_units=j.get('liquidityUnits', '0'),
            basis_points=j.get('basisPoints', '0'),
            impermanent_loss_protection=j.get('impermanentLossProtection', '0')
        )


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

    @staticmethod
    def merge_two(a: 'ThorMetaAddLiquidity', b: 'ThorMetaAddLiquidity'):
        if a and b:
            return ThorMetaAddLiquidity(
                liquidity_units=sum_and_str(a.liquidity_units, b.liquidity_units)
            )
        else:
            return a or b


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
    affiliate_fee: float = 0.0  # (0..1) range

    # extended properties

    # for add, withdraw, donate
    address_rune: str = ''
    address_asset: str = ''
    tx_hash_rune: str = ''
    tx_hash_asset: str = ''
    asset_amount: float = 0.0
    rune_amount: float = 0.0

    # filled by "calc_full_rune_amount"
    full_rune: float = 0.0  # TX volume
    asset_per_rune: float = 0.0

    dex_info: SwapInOut = SwapInOut()

    is_savings: bool = False

    def sort_inputs_by_first_asset(self):
        self.in_tx.sort(key=lambda sub_tx: (sub_tx.coins[0].asset if sub_tx.coins else ''))

    @property
    def is_success(self):
        return self.status == SUCCESS

    @property
    def is_pending(self):
        return self.status == PENDING

    @property
    def date_timestamp(self):
        return int(int(self.date) * 1e-9)

    @property
    def age_sec(self):
        return now_ts() - self.date_timestamp

    @property
    def height_int(self):
        return int(self.height)

    @property
    def tx_hash(self):
        sub_tx_set = self.in_tx or self.out_tx
        if not sub_tx_set:
            return self.date
        hashes = [sub_tx.tx_id for sub_tx in sub_tx_set]
        hashes.sort()
        return hashes[0]

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
        return self.out_tx[0] if self.out_tx else None

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
            if not tx.coins and LPAddress.is_thor_prefix(tx.address):
                # in the case when it is "empty" thor tx (with no coins sent)
                return tx.address

            for coin in tx.coins:
                if is_rune(coin.asset):
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

        return None, None

    def search_realm(self, in_only=False, out_only=False):
        return self.in_tx if in_only else self.out_tx if out_only else self.in_tx + self.out_tx

    def get_sub_tx(self, asset, in_only=False, out_only=False):
        for sub_tx in self.search_realm(in_only, out_only):
            for coin in sub_tx.coins:
                if asset == coin.asset:
                    return sub_tx
                elif is_rune(asset) and is_rune(coin.asset):
                    return sub_tx

    def coins_of(self, in_only=False, out_only=False):
        return (coin for sub_tx in self.search_realm(in_only, out_only) for coin in sub_tx.coins)

    def sum_of(self, predicate, in_only=False, out_only=False):
        return sum(coin.amount_float for coin in self.coins_of(in_only, out_only) if predicate(coin))

    def sum_of_asset(self, asset, in_only=False, out_only=False):
        return self.sum_of(lambda c: c.asset == asset, in_only, out_only)

    def sum_of_non_rune(self, in_only=False, out_only=False):
        return self.sum_of(lambda c: not is_rune(c.asset), in_only, out_only)

    def sum_of_rune(self, in_only=False, out_only=False):
        return self.sum_of(lambda c: is_rune(c.asset), in_only, out_only)

    def get_asset_summary(self, in_only=False, out_only=False, short_name=True):
        results = defaultdict(float)
        for coin in self.coins_of(in_only, out_only):
            name = Asset(coin.asset).short_str if short_name else coin.asset
            results[name] += coin.amount_float
        return results

    def not_rune_asset(self, in_only=False, out_only=False):
        for coin in self.coins_of(in_only, out_only):
            if not is_rune(coin):
                return coin

    @property
    def first_pool(self):
        return self.pools[0] if self.pools else None

    @property
    def first_pool_l1(self):
        return Asset.to_L1_pool_name(self.first_pool)

    def __hash__(self) -> int:
        return int(self.tx_hash, 16)

    def __eq__(self, other):
        if isinstance(other, ThorTx):
            return self.height_int == other.height_int and self.tx_hash == other.tx_hash and self.type == other.type
        else:
            return False

    def deep_eq(self, other: 'ThorTx'):
        if other != self:
            return False
        if len(other.in_tx) != len(self.in_tx):
            return False
        for in1, in2 in zip(self.in_tx, other.in_tx):
            if in1.address != in2.address or in1.tx_id != in2.tx_id or len(in1.coins) != len(in2.coins):
                return False
            for c1, c2 in zip(in1.coins, in2.coins):
                if c1.asset != c2.asset or c1.amount != c2.amount:
                    return False

        return True

    @property
    def is_synth_involved(self):
        for sub_tx in self.search_realm():
            for c in sub_tx.coins:
                if '/' in c.asset:
                    return True
        return False

    @property
    def is_liquidity_type(self):
        return self.type in (ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_ADD_LIQUIDITY)

    # extended methods and properties
    def __post_init__(self):
        t = self.type
        if t == ThorTxType.TYPE_ADD_LIQUIDITY or t == ThorTxType.TYPE_DONATE:
            pool = self.first_pool  # add maybe both synth (means savers) or l1 (normal liquidity)
            self.rune_amount = self.sum_of_rune(in_only=True)
            self.asset_amount = self.sum_of_asset(pool, in_only=True)

            rune_sub_tx = self.get_sub_tx(RUNE_SYMBOL, in_only=True)
            self.address_rune = rune_sub_tx.address if rune_sub_tx else None
            self.tx_hash_rune = rune_sub_tx.tx_id if rune_sub_tx else None

            asset_sub_tx = self.get_sub_tx(pool, in_only=True)
            self.address_asset = asset_sub_tx.address if asset_sub_tx else None
            self.tx_hash_asset = asset_sub_tx.tx_id if asset_sub_tx else None

        elif t == ThorTxType.TYPE_WITHDRAW:
            pool = self.first_pool_l1  # withdraw always l1 no matter it was savers or normal liquidity
            self.rune_amount = self.sum_of_rune(out_only=True)
            self.asset_amount = self.sum_of_asset(pool, out_only=True)

            sub_tx_rune = self.get_sub_tx(RUNE_SYMBOL, in_only=True)
            self.address_rune = sub_tx_rune.address if sub_tx_rune else self.in_tx[0].address

            out_sub_tx_rune = self.get_sub_tx(RUNE_SYMBOL, out_only=True)
            out_sub_tx_asset = self.get_sub_tx(pool, out_only=True)
            self.tx_hash_rune = out_sub_tx_rune.tx_id if out_sub_tx_rune else None
            self.tx_hash_asset = out_sub_tx_asset.tx_id if out_sub_tx_asset else None

        elif t == ThorTxType.TYPE_SWITCH:
            # rune_amount <= asset_amount when the kill switch is active!
            self.rune_amount = self.sum_of_rune(out_only=True)
            self.asset_amount = self.sum_of_non_rune(in_only=True)

        elif t in (ThorTxType.TYPE_REFUND, ThorTxType.TYPE_SWAP):
            # only outputs
            self.rune_amount = self.sum_of_rune(out_only=True)
            self.asset_amount = self.sum_of_non_rune(out_only=True)

            if t == ThorTxType.TYPE_SWAP:
                self.affiliate_fee = self.meta_swap.affiliate_fee

        self.is_savings = any(True for asset in self.pools if Asset.from_string(asset).is_synth)

    def asymmetry(self, force_abs=False):
        rune_asset_amount = self.asset_amount * self.asset_per_rune
        factor = (self.rune_amount / (rune_asset_amount + self.rune_amount) - 0.5) * 200.0  # -100 % ... + 100 %
        return abs(factor) if force_abs else factor

    def symmetry_rune_vs_asset(self):
        if not self.full_rune:
            return 0.0, 0.0

        f = 100.0 / self.full_rune
        if self.asset_per_rune == 0.0:
            return 0.0, 0.0
        else:
            return self.rune_amount * f, self.asset_amount / self.asset_per_rune * f

    @staticmethod
    def calc_amount(pool_map: PoolInfoMap, realm):
        rune_sum = 0.0
        for tx in realm:
            for coin in tx.coins:
                if is_rune(coin.asset):
                    rune_sum += coin.amount_float
                else:
                    pool_name = Asset.to_L1_pool_name(coin.asset)
                    pool_info = pool_map.get(pool_name)
                    if pool_info:
                        rune_sum += pool_info.runes_per_asset * coin.amount_float

        return rune_sum

    def calc_full_rune_amount(self, pool_map: PoolInfoMap = None):
        if self.type == ThorTxType.TYPE_SWITCH:
            r = self.rune_amount
        else:
            # We take price in from the L1 pool, that's why convert_synth_to_pool_name is used
            pool_info: PoolInfo = pool_map.get(self.first_pool_l1)

            self.asset_per_rune = pool_info.asset_per_rune if pool_info else 0.0

            if self.type in (ThorTxType.TYPE_SWAP, ThorTxType.TYPE_WITHDRAW):
                r = self.calc_amount(pool_map, self.search_realm(out_only=True))
            else:
                # add, donate, refund
                r = self.calc_amount(pool_map, self.search_realm(in_only=True))
        self.full_rune = r
        return self.full_rune

    def get_usd_volume(self, usd_per_rune):
        return usd_per_rune * self.full_rune

    def what_percent_of_pool(self, pool_info: PoolInfo) -> float:
        percent_of_pool = 100.0
        if pool_info:
            correction = self.full_rune if self.type == ThorTxType.TYPE_WITHDRAW else 0.0
            percent_of_pool = pool_info.percent_share(self.full_rune, correction)
        return percent_of_pool

    def get_affiliate_fee_usd(self, usd_per_rune):
        return self.affiliate_fee * self.get_usd_volume(usd_per_rune)

    @property
    def dex_aggregator_used(self):
        return bool(self.dex_info.swap_in) or bool(self.dex_info.swap_out)


def final_liquidity(txs: List[ThorTx]):
    lp = 0
    for tx in txs:
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            lp += tx.meta_add.liquidity_units_int
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            lp += tx.meta_withdraw.liquidity_units_int
    return lp


def cut_off_previous_lp_sessions(txs: List[ThorTx]):
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
class EventLargeTransaction:
    transaction: ThorTx
    usd_per_rune: float
    pool_info: PoolInfo
    cap_info: ThorCapInfo = None
    mimir: MimirHolder = None

