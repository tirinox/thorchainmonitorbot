import string
import time
from dataclasses import dataclass, field
from math import sqrt
from typing import List, Dict

from services.lib.constants import THOR_DIVIDER_INV, Chains
from services.lib.date_utils import DAY
from services.models.base import BaseModelMixin
from services.models.pool_info import PoolInfo, LPPosition, pool_share

BECH_2_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


@dataclass
class LPAddress(BaseModelMixin):
    address: str = ''
    chain: str = Chains.BNB
    pools: list = field(default_factory=list)

    @classmethod
    def is_good_bnb_address(cls, addr: str):
        addr = addr.strip()
        return (addr.startswith('bnb1')
                and 30 <= len(addr) <= 50
                and set(addr[4:]) < set(BECH_2_CHARSET))

    @classmethod
    def is_thor_prefix(cls, addr: str):
        addr = addr.lower()
        return addr.startswith('tthor') or addr.startswith('thor')

    @classmethod
    def validate_address(cls, addr: str):
        addr = addr.strip()
        if not (26 <= len(addr) <= 78):
            return False
        # if not cls.is_thor_prefix(addr):
        #     return False

        english_and_numbers = string.ascii_letters + string.digits
        if not all(c in english_and_numbers for c in addr):
            return False

        return addr.isalnum()


@dataclass
class LPDailyGraphPoint:
    timestamp: int = 0
    usd_value: float = 0

    @classmethod
    def from_asgard(cls, j):
        asset_depth = int(j.get('assetdepth', 1))
        rune_depth = int(j.get('runedepth', 1))
        busd_rune_price = float(j.get('busdpricerune', 1.0))
        pool_units = int(j.get('poolunits', 1))
        stake_units = int(j.get('stakeunit', 1))

        r, a = pool_share(rune_depth, asset_depth, stake_units, pool_units)
        runes_per_asset = rune_depth / asset_depth
        total_rune = r * THOR_DIVIDER_INV + a * THOR_DIVIDER_INV * runes_per_asset
        usd_value = total_rune / busd_rune_price

        return cls(
            usd_value=usd_value,
            timestamp=int(j.get('time', 0)),
        )


LPDailyChartByPoolDict = Dict[str, List[LPDailyGraphPoint]]


@dataclass
class CurrentLiquidity(BaseModelMixin):
    pool: str
    rune_stake: float
    asset_stake: float
    pool_units: int
    asset_withdrawn: float
    rune_withdrawn: float
    total_staked_asset: float
    total_staked_rune: float
    total_staked_usd: float
    total_unstaked_asset: float
    total_unstaked_rune: float
    total_unstaked_usd: float
    first_stake_ts: int
    last_stake_ts: int

    @classmethod
    def from_asgard(cls, d):
        m = THOR_DIVIDER_INV
        return cls(
            d['pool'],
            float(d['runestake']) * m,
            float(d['assetstake']) * m,
            int(d['poolunits']),
            float(d['assetwithdrawn']) * m,
            float(d['runewithdrawn']) * m,
            float(d['totalstakedasset']) * m,
            float(d['totalstakedrune']) * m,
            float(d['totalstakedusd']) * m,
            float(d['totalunstakedasset']) * m,
            float(d['totalunstakedrune']) * m,
            float(d['totalunstakedusd']) * m,
            int(d['firststake']),
            int(d['laststake'])
        )


@dataclass
class FeeReport:
    asset: str = ''
    imp_loss_usd: float = 0.0
    imp_loss_percent: float = 0.0
    fee_usd: float = 0.0
    fee_rune: float = 0.0
    fee_asset: float = 0.0

    @classmethod
    def parse_from_asgard(cls, j):
        return cls(
            asset=j['asset'],
            imp_loss_usd=float(j['impLoss']['usd']),
            imp_loss_percent=float(j['impLoss']['percent']),
            fee_usd=float(j['fee']['usd']),
            fee_rune=float(j['fee']['rune']),
            fee_asset=float(j['fee']['asset']),
        )


@dataclass
class ILProtectionReport:
    progress_progress: float = 0.0  # up to 1.0 (full)
    rune_compensation: float = 0.0
    max_rune_compensation: float = 0.0  # if it is 100%
    cover_of_asset: float = 0.0  # extra amount on withdraw
    cover_of_rune: float = 0.0  # extra amount on withdraw


@dataclass
class ReturnMetrics:
    hold_return: float = 0.0
    net_return: float = 0.0
    uniswap_return: float = 0.0
    imp_loss: float = 0.0
    fees_usd: float = 0.0
    imp_loss_percentage: float = 0.0

    @classmethod
    def from_position_window(cls, p0: LPPosition, p1: LPPosition):
        t0_ownership = p0.liquidity_units / p0.liquidity_total
        t1_ownership = p1.liquidity_units / p1.liquidity_total

        t0_rune_amount = t0_ownership * p0.rune_balance
        t0_asset_amount = t0_ownership * p0.asset_balance

        t1_rune_amount = t1_ownership * p1.rune_balance
        t1_asset_amount = t1_ownership * p1.asset_balance

        t0_asset_value = t0_rune_amount * p0.usd_per_rune + t0_asset_amount * p0.usd_per_asset
        t1_asset_value_hold = t0_rune_amount * p1.usd_per_rune + t0_asset_amount * p1.usd_per_asset

        # we use XYK formula to just get asset and rune amount based ONLY on price change, no fees and rewards are added

        sqrt_k_t0 = sqrt(t0_rune_amount * t0_asset_amount)
        price_ratio_t1 = p1.usd_per_asset / p1.usd_per_rune if p1.usd_per_rune else 0.0

        rune_amount_no_fees = sqrt_k_t0 * sqrt(price_ratio_t1) if p1.usd_per_asset and price_ratio_t1 else 0.0
        asset_amount_no_fees = sqrt_k_t0 / sqrt(price_ratio_t1) if p1.usd_per_asset and price_ratio_t1 else 0.0
        usd_no_fees = rune_amount_no_fees * p1.usd_per_rune + asset_amount_no_fees * p1.usd_per_asset

        difference_fees_rune = t1_rune_amount - rune_amount_no_fees
        difference_fees_asset = t1_asset_amount - asset_amount_no_fees
        difference_fees_usd = difference_fees_rune * p1.usd_per_rune + difference_fees_asset * p1.usd_per_asset

        # fixme: invalid calculation
        imp_loss_usd = usd_no_fees - t1_asset_value_hold
        uniswap_return = difference_fees_usd + imp_loss_usd

        t0_net_value = t0_ownership * p0.total_usd_balance
        t1_net_value = t1_ownership * p1.total_usd_balance

        hold_return = t1_asset_value_hold - t0_asset_value
        net_return = t1_net_value - t0_net_value
        a_sum = (p0.usd_per_rune * t1_rune_amount + p0.usd_per_asset * t0_asset_amount)
        percentage = imp_loss_usd / a_sum if a_sum != 0.0 else 0.0

        return cls(hold_return, net_return, uniswap_return, imp_loss_usd, difference_fees_usd, percentage)

    def __add__(self, other: 'ReturnMetrics'):
        return ReturnMetrics(
            self.hold_return + other.hold_return,
            self.net_return + other.net_return,
            self.uniswap_return + other.uniswap_return,
            self.imp_loss + other.imp_loss,
            self.fees_usd + other.fees_usd,
            self.imp_loss_percentage + other.imp_loss_percentage
        )


@dataclass
class FeeRequest:
    height: int = 0
    pair: str = ''
    liquidity_token_balance: float = 0.0
    liquidity_token_supply: float = 0.0
    reserve_0: float = 0.0
    reserve_1: float = 0.0
    reserve_usdt: float = 0.0
    reserve_token_0_price_usd: float = 0.0
    reserve_token_1_price_usd: float = 0.0

    @classmethod
    def parse_from_asgard(cls, j):
        return cls(
            height=int(j.get('height', 0)),
            pair=j.get('pair', ''),
            liquidity_token_balance=float(j.get('liquidityTokenBalance', 0.0)),
            liquidity_token_supply=float(j.get('liquidityTokenTotalSupply', 0.0)),
            reserve_0=float(j.get('reserve0', 0.0)),
            reserve_1=float(j.get('reserve1', 0.0)),
            reserve_usdt=float(j.get('reserveUSD', 0.0)),
            reserve_token_0_price_usd=float(j.get('token0PriceUSD', 0.0)),
            reserve_token_1_price_usd=float(j.get('token1PriceUSD', 0.0)),
        )


@dataclass
class LiquidityPoolReport:
    usd_per_asset: float
    usd_per_rune: float

    usd_per_asset_start: float
    usd_per_rune_start: float

    liq: CurrentLiquidity
    fees: FeeReport
    pool: PoolInfo
    protection: ILProtectionReport

    ASSET = 'asset'
    RUNE = 'rune'
    USD = 'usd'

    def price_change(self, mode=USD):
        if mode == self.USD:
            return 0.0
        elif mode == self.RUNE:
            return (self.usd_per_rune / self.usd_per_rune_start - 1) * 100.0
        elif mode == self.ASSET:
            return (self.usd_per_asset / self.usd_per_asset_start - 1) * 100.0

    @property
    def lp_vs_hold(self) -> (float, float):
        rune_added_in_usd = self.liq.rune_stake * self.usd_per_rune
        asset_added_in_usd = self.liq.asset_stake * self.usd_per_asset
        total_added_in_usd = rune_added_in_usd + asset_added_in_usd

        rune_withdrawn_in_usd = self.liq.rune_withdrawn * self.usd_per_rune
        asset_withdrawn_in_usd = self.liq.asset_withdrawn * self.usd_per_asset
        total_withdrawn_in_usd = rune_withdrawn_in_usd + asset_withdrawn_in_usd

        redeem_rune, redeem_asset = self.redeemable_rune_asset
        redeem_rune_in_usd = redeem_rune * self.usd_per_rune
        redeem_asset_in_usd = redeem_asset * self.usd_per_asset
        total_redeemable_in_usd = redeem_rune_in_usd + redeem_asset_in_usd

        lp_vs_hold_abs = total_redeemable_in_usd + total_withdrawn_in_usd - total_added_in_usd
        lp_vs_hold_percent = lp_vs_hold_abs / total_added_in_usd * 100.0
        return lp_vs_hold_abs, lp_vs_hold_percent

    @property
    def total_days(self):
        total_days = self.total_staking_sec / DAY
        return total_days

    @property
    def lp_vs_hold_apy(self) -> float:
        _, lp_vs_hold_percent = self.lp_vs_hold
        lp_vs_hold_percent /= 100.0
        apy = (1 + lp_vs_hold_percent / self.total_days) ** 365 - 1
        return apy * 100.0

    def gain_loss(self, mode=USD) -> (float, float):
        cur_val = self.current_value(mode)
        wth_val = self.withdrawn_value(mode)
        add_val = self.added_value(mode)
        gain_loss_abs = cur_val + wth_val - add_val
        gain_loss_percent = gain_loss_abs / add_val * 100.0
        return gain_loss_abs, gain_loss_percent

    @property
    def gain_loss_raw(self):
        redeem_rune, redeem_asset = self.redeemable_rune_asset
        gl_rune = self.liq.rune_withdrawn + redeem_rune - self.liq.rune_stake
        gl_asset = self.liq.asset_withdrawn + redeem_asset - self.liq.asset_stake
        gl_rune_per = gl_rune / self.liq.rune_stake * 100.0 if self.liq.rune_stake != 0 else 0.0
        gl_asset_per = gl_asset / self.liq.asset_stake * 100.0 if self.liq.asset_stake != 0 else 0.0
        return gl_rune, gl_rune_per, gl_asset, gl_asset_per

    @property
    def usd_gain_loss_percent(self):
        gl_rune, gl_rune_per, gl_asset, gl_asset_per = self.gain_loss_raw
        gl_usd = gl_rune * self.usd_per_rune + gl_asset * self.usd_per_asset
        gl_usd_per = gl_usd / self.added_value(self.USD) * 100.0
        return gl_usd_per

    @property
    def redeemable_rune_asset(self):
        r, a = pool_share(self.pool.balance_rune, self.pool.balance_asset, self.liq.pool_units, self.pool.pool_units)
        return r * THOR_DIVIDER_INV, a * THOR_DIVIDER_INV

    def added_value(self, mode=USD):
        if mode == self.USD:
            return self.liq.total_staked_usd
        elif mode == self.RUNE:
            return self.liq.total_staked_rune
        elif mode == self.ASSET:
            return self.liq.total_staked_asset

    def withdrawn_value(self, mode=USD):
        if mode == self.USD:
            return self.liq.total_unstaked_usd
        elif mode == self.RUNE:
            return self.liq.total_unstaked_rune
        elif mode == self.ASSET:
            return self.liq.total_unstaked_asset

    def current_value(self, mode=USD):
        r, a = self.redeemable_rune_asset
        usd_value = r * self.usd_per_rune + a * self.usd_per_asset
        if mode == self.USD:
            return usd_value
        elif mode == self.RUNE:
            return usd_value / self.usd_per_rune
        elif mode == self.ASSET:
            return usd_value / self.usd_per_asset

    @property
    def total_staking_sec(self):
        return int(time.time()) - self.liq.first_stake_ts

    def fee_value(self, mode=USD):
        if mode == self.USD:
            return self.fees.fee_usd
        elif mode == self.RUNE:
            return self.fees.fee_rune
        else:
            return self.fees.fee_asset

    def il_protection_value(self, mode=USD):
        if mode == self.USD:
            return self.protection.rune_compensation * self.usd_per_rune
        elif mode == self.RUNE:
            return self.protection.rune_compensation
        elif mode == self.ASSET:
            return self.protection.rune_compensation * self.usd_per_rune / self.usd_per_asset
