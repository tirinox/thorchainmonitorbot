import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, NamedTuple

from api.aionode.types import ThorSwapperClout
from api.w3.token_record import SwapInOut
from lib.constants import Chains, thor_to_float, bp_to_float, THOR_BLOCK_TIME
from lib.date_utils import now_ts
from lib.texts import safe_sum
from .asset import Asset, is_rune, Delimiter, AssetKind
from .cap_info import ThorCapInfo
from .lp_info import LPAddress
from .memo import ActionType, is_action
from .memo import THORMemo
from .mimir import MimirHolder
from .pool_info import PoolInfo, PoolInfoMap
from .price import PriceHolder
from .s_swap import StreamingSwap

logger = logging.getLogger('ThorTx')


class ThorCoin(NamedTuple):
    amount: int = 0
    asset: str = ''

    @property
    def amount_float(self):
        return thor_to_float(self.amount)

    @staticmethod
    def merge_two(a: 'ThorCoin', b: 'ThorCoin'):
        assert a.asset == b.asset
        return ThorCoin(safe_sum(a.amount, b.amount), a.asset)

    @classmethod
    def from_json(cls, j):
        return cls(int(j.get('amount', 0)), j.get('asset', ''))


@dataclass
class ThorSubTx:
    address: str
    coins: List[ThorCoin]
    tx_id: str
    height: int = 0
    is_affiliate: bool = False
    is_refund: bool = False

    @classmethod
    def parse(cls, j):
        coins = [ThorCoin.from_json(cj) for cj in j.get('coins', [])]
        return cls(
            address=j.get('address', ''),
            coins=coins,
            tx_id=j.get('txID', ''),
            height=int(j.get('height', 0)),
            is_affiliate=j.get('affiliate', False)
        )

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
    liquidity_fee: int
    network_fees: List[ThorCoin]
    trade_slip: int
    trade_target: int
    affiliate_fee: float = 0.0  # (0..1) range
    memo: str = ''
    affiliate_address: str = ''  # highly likely to be a THORName
    streaming: Optional[StreamingSwap] = None

    tx_type: str = ''  # swap/loan/...
    is_streaming_swap: bool = False

    cex_out_amount: float = 0.0

    estimated_savings_vs_cex_usd: float = 0.0

    @classmethod
    def parse(cls, j):
        fees = [ThorCoin.from_json(cj) for cj in j.get('networkFees', [])]
        return cls(
            liquidity_fee=int(j.get('liquidityFee', 0)),
            network_fees=fees,
            trade_slip=int(j.get('swapSlip', '0')),
            trade_target=int(j.get('swapTarget', '0')),
            affiliate_fee=bp_to_float(j.get('affiliateFee', 0)),
            affiliate_address=j.get('affiliateAddress', ''),
            memo=j.get('memo', ''),
            tx_type=j.get('txType', ''),
            is_streaming_swap=j.get('isStreamingSwap', False),
        )

    @property
    def trade_slip_percent(self):
        return int(self.trade_slip) / 100.0

    @property
    def liquidity_fee_rune_float(self):
        return thor_to_float(self.liquidity_fee)

    def liquidity_fee_in_percent(self, full_rune_volume):
        return self.liquidity_fee_rune_float / full_rune_volume * 100.0

    @staticmethod
    def merge_two(a: 'ThorMetaSwap', b: 'ThorMetaSwap'):
        if a and b:
            return ThorMetaSwap(
                liquidity_fee=safe_sum(a.liquidity_fee, b.liquidity_fee),
                network_fees=a.network_fees + b.network_fees,
                trade_slip=safe_sum(a.trade_slip, b.trade_slip),
                trade_target=safe_sum(a.trade_target, b.trade_target),
                affiliate_fee=max(a.affiliate_fee, b.affiliate_fee),
                affiliate_address=a.affiliate_address if a.affiliate_address else b.affiliate_address,
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
        fees = [ThorCoin.from_json(cj) for cj in j.get('networkFees', [])]
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
        fees = [ThorCoin.from_json(cj) for cj in j.get('networkFees', [])]
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
                liquidity_units=safe_sum(a.liquidity_units, b.liquidity_units)
            )
        else:
            return a or b


SUCCESS = 'success'
PENDING = 'pending'


@dataclass
class ThorAction:
    date: int
    height: int
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
    asset_amount: float = 0.0
    rune_amount: float = 0.0

    # filled by "calc_full_rune_amount"
    full_volume_in_rune: float = 0.0  # TX volume
    asset_per_rune: float = 0.0

    dex_info: SwapInOut = SwapInOut()

    def is_of_type(self, t):
        if isinstance(t, (tuple, list, set)):
            return any(is_action(self.type, tp) for tp in t)
        else:
            return is_action(self.type, t)

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
    def tx_hash(self):
        sub_tx_set = self.in_tx or self.out_tx
        if not sub_tx_set:
            return self.date
        hashes = [sub_tx.tx_id for sub_tx in sub_tx_set if sub_tx.tx_id]
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
    def recipient_address(self) -> Optional[str]:
        r = self.recipients_output
        return r.address if r else None

    @property
    def recipients_output(self) -> Optional[ThorSubTx]:
        return next((tx for tx in self.out_tx if not tx.is_affiliate and not tx.is_refund), None)

    @property
    def has_refund_output(self):
        return any(True for tx in self.out_tx if tx.is_refund)

    @property
    def all_addresses(self):
        return [
            tx.address for tx in self.in_tx + self.out_tx
        ]

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

    @property
    def all_realms(self):
        return self.in_tx + self.out_tx

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

    def get_asset_summary(self, in_only=False, out_only=False):
        results = defaultdict(float)
        for coin in self.coins_of(in_only, out_only):
            results[coin.asset] += coin.amount_float
        return results

    def not_rune_asset(self, in_only=False, out_only=False):
        for coin in self.coins_of(in_only, out_only):
            if not is_rune(coin.asset):
                return coin

    @property
    def first_pool(self):
        return self.pools[0] if self.pools else None

    @property
    def first_pool_l1(self):
        if self.first_pool:
            pool = self.first_pool
        elif self.first_input_tx:
            pool = self.first_input_tx.first_asset
        elif self.first_output_tx:
            pool = self.first_output_tx.first_asset
        else:
            raise ValueError('Unable to determine pool')
        return Asset.to_L1_pool_name(pool)

    def __hash__(self) -> int:
        return int(self.tx_hash, 16)

    def __eq__(self, other):
        if isinstance(other, ThorAction):
            return self.height == other.height and self.tx_hash == other.tx_hash and self.type == other.type
        else:
            return False

    def deep_eq(self, other: 'ThorAction'):
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
    def all_assets(self):
        return set(c.asset for c in self.coins_of())

    @property
    def is_synth_involved(self):
        return any(True for a in self.all_assets if Delimiter.SYNTH in a)

    @property
    def is_trade_asset_involved(self):
        return any(True for a in self.all_assets if Delimiter.TRADE in a)

    @property
    def is_secured_asset_involved(self):
        return any(True for a in self.all_assets if AssetKind.recognize(a) == AssetKind.SECURED)

    @property
    def is_liquidity_type(self):
        return self.is_of_type((ActionType.ADD_LIQUIDITY, ActionType.WITHDRAW))

    # extended methods and properties
    def __post_init__(self):
        if self.is_of_type((ActionType.ADD_LIQUIDITY, ActionType.DONATE)):
            pool = self.first_pool  # add maybe both synth (means savers) or l1 (normal liquidity)
            self.rune_amount = self.sum_of_rune(in_only=True)
            self.asset_amount = self.sum_of_asset(pool, in_only=True)

        elif self.is_of_type(ActionType.WITHDRAW):
            pool = self.first_pool_l1  # withdraw always l1 no matter it was savers or normal liquidity
            self.rune_amount = self.sum_of_rune(out_only=True)
            self.asset_amount = self.sum_of_asset(pool, out_only=True)

        elif self.is_of_type((ActionType.REFUND, ActionType.SWAP)):
            # only outputs
            self.rune_amount = self.sum_of_rune(out_only=True)
            self.asset_amount = self.sum_of_non_rune(out_only=True)

            if self.is_of_type(ActionType.SWAP):
                self.affiliate_fee = self.meta_swap.affiliate_fee

    def asymmetry(self, force_abs=False):
        rune_asset_amount = self.asset_amount * self.asset_per_rune
        factor = (self.rune_amount / (rune_asset_amount + self.rune_amount) - 0.5) * 200.0  # -100 % ... + 100 %
        return abs(factor) if force_abs else factor

    def symmetry_rune_vs_asset(self):
        if not self.full_volume_in_rune:
            return 0.0, 0.0

        f = 100.0 / self.full_volume_in_rune
        if self.asset_per_rune == 0.0:
            return 0.0, 0.0
        else:
            return self.rune_amount * f, self.asset_amount / self.asset_per_rune * f

    @staticmethod
    def calc_amount(pool_map: PoolInfoMap, realm, filter_unknown_runes=False):
        """
        Full Rune volume of the TX
        @param pool_map: Pool map
        @param realm: List of ThorSubTx
        @param filter_unknown_runes: forces it to not count Rune-coins if tx_id is empty.
        This is needed to fit Midgard peculiarity for savers withdrawals. See the example:
        https://midgard.ninerealms.com/v2/actions?txid=C24DF9D0A379519EBEEF2DBD50F5AD85AB7A5B75A2F3C571E185202EE2E9876F
        @return: float
        """
        rune_sum = 0.0
        for tx in realm:
            for coin in tx.coins:
                if is_rune(coin.asset):
                    if filter_unknown_runes and not tx.tx_id:
                        continue
                    rune_sum += coin.amount_float
                else:
                    pool_name = Asset.to_L1_pool_name(coin.asset)
                    pool_info = pool_map.get(pool_name)
                    if pool_info:
                        rune_sum += pool_info.runes_per_asset * coin.amount_float

        return rune_sum

    def calc_full_rune_amount(self, pool_map: PoolInfoMap = None):
        # We take price in from the L1 pool, that's why convert_synth_to_pool_name is used
        pool_info: PoolInfo = pool_map.get(self.first_pool_l1)

        self.asset_per_rune = pool_info.asset_per_rune if pool_info else 0.0

        if self.is_of_type((ActionType.SWAP, ActionType.WITHDRAW)):
            if self.is_pending and not self.out_tx:
                # pending txs have no out_tx, so we use in_tx
                realm = self.search_realm(in_only=True)
            else:
                realm = self.search_realm(out_only=True)
            r = self.calc_amount(pool_map, realm)
        elif self.is_of_type((ActionType.TRADE_ACC_WITHDRAW, ActionType.TRADE_ACC_DEPOSIT)):
            r = self.calc_amount(pool_map, self.all_realms)
        else:
            # add, donate, refund
            r = self.calc_amount(pool_map, self.search_realm(in_only=True))
        self.full_volume_in_rune = r

        if self.full_volume_in_rune == 0.0:
            logger.warning(f'Tx {self} has ZERO Rune amount!')

        return self.full_volume_in_rune

    def get_usd_volume(self, usd_per_rune):
        return usd_per_rune * self.full_volume_in_rune

    def what_percent_of_pool(self, pool_info: PoolInfo) -> float:
        percent_of_pool = 100.0
        if pool_info:
            correction = self.full_volume_in_rune if self.is_of_type(ActionType.WITHDRAW) else 0.0
            percent_of_pool = pool_info.percent_share(self.full_volume_in_rune, correction)
        return percent_of_pool

    def get_affiliate_fee_usd(self, usd_per_rune):
        return self.affiliate_fee * self.get_usd_volume(usd_per_rune)

    @property
    def dex_aggregator_used(self):
        return bool(self.dex_info.swap_in) or bool(self.dex_info.swap_out)

    @property
    def is_streaming(self):
        return bool(self.meta_swap and self.meta_swap.streaming and self.meta_swap.streaming.quantity > 1)

    @property
    def memo(self) -> THORMemo:
        meta = self.meta_swap or self.meta_add or self.meta_withdraw or self.meta_refund
        if hasattr(meta, 'memo'):
            return THORMemo.parse_memo(meta.memo)

    def first_out_coin_other_than_input(self):
        in_assets = set(a.first_asset for a in self.in_tx)
        return next((
            coin
            for sub_tx in self.out_tx
            for coin in sub_tx.coins
            if coin.asset not in in_assets
        ), None)

    @property
    def swap_profit_vs_cex(self):
        if not self.meta_swap:
            return

        real_out = thor_to_float(self.first_out_coin_other_than_input().amount)
        cex_out = self.meta_swap.cex_out_amount
        return real_out - cex_out

    @property
    def percent_profit_vs_cex(self):
        if not self.meta_swap:
            return

        real_out = thor_to_float(self.first_out_coin_other_than_input().amount)
        cex_out = self.meta_swap.cex_out_amount
        return (real_out - cex_out) / cex_out * 100.0 if cex_out else None

    def get_profit_vs_cex_in_usd(self, price_holder: PriceHolder):
        profit_out_asset = self.swap_profit_vs_cex
        if profit_out_asset is None:
            return

        out_coin = self.first_out_coin_other_than_input()

        return price_holder.convert_to_usd(profit_out_asset, out_coin.asset)

    @property
    def refund_coin(self) -> Optional[ThorCoin]:
        in_tx = self.first_input_tx
        if in_tx and in_tx.coins:
            in_coin = in_tx.coins[0]
            for out_tx in self.out_tx:
                for coin in out_tx.coins:
                    if coin.asset == in_coin.asset:
                        return coin

    @property
    def any_side_in_tc(self):
        return any(
            c for c in self.coins_of()
            if is_rune(c.asset) or Asset(c.asset).is_trade or Asset(c.asset).is_synth
        )

    @property
    def liquidity_fee_percent(self):
        if not self.meta_swap:
            return 0.0
        return self.meta_swap.liquidity_fee_in_percent(self.full_volume_in_rune)

    @property
    def latest_outbound_height(self):
        return max(tx.height for tx in self.out_tx)

    @property
    def duration(self) -> float:
        if self.is_success:
            height = self.height
            latest_outbound_height = self.latest_outbound_height
            blocks = latest_outbound_height - height
            if height == latest_outbound_height > 0:
                blocks = 1  # min 1 block to process
            return blocks * THOR_BLOCK_TIME
        return 0.0


@dataclass
class EventLargeTransaction:
    transaction: ThorAction
    usd_per_rune: float
    pool_info: PoolInfo
    cap_info: Optional[ThorCapInfo] = None
    mimir: Optional[MimirHolder] = None
    details: Optional[dict] = None
    clout: Optional[ThorSwapperClout] = None

    # For swaps
    usd_volume_input: float = 0.0
    usd_volume_output: float = 0.0

    @property
    def is_swap(self):
        return self.transaction.is_of_type(ActionType.SWAP)

    @property
    def begin_height(self):
        # consensus_height = self.details.get('consensus_height') if self.details else 0
        # return consensus_height or self.transaction.height
        return self.transaction.height

    @property
    def duration(self):
        return self.transaction.duration
