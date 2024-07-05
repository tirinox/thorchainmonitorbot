import string
from dataclasses import dataclass, field
from math import sqrt
from typing import List, Dict

from services.lib.constants import thor_to_float
from services.lib.date_utils import DAY, now_ts
from services.models.base import BaseModelMixin
from services.models.pool_info import PoolInfo, pool_share

BECH_2_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def change_ratio_to_apy(ch, days):
    return 100.0 * ((1.0 + (ch / days)) ** 365 - 1.0)


@dataclass
class LPAddress(BaseModelMixin):
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
class LPPosition:
    pool: str
    liquidity_units: int
    liquidity_total: int
    rune_balance: float
    asset_balance: float
    usd_per_rune: float
    usd_per_asset: float
    total_usd_balance: float

    @classmethod
    def create(cls, pool: PoolInfo, my_units: int, usd_per_rune: float):
        usd_per_asset = usd_per_rune / pool.asset_per_rune
        return cls(
            pool=pool.asset,
            liquidity_units=my_units,
            liquidity_total=pool.units if pool.units else pool.pool_units,
            rune_balance=thor_to_float(pool.balance_rune),
            asset_balance=thor_to_float(pool.balance_asset),
            usd_per_rune=usd_per_rune,
            usd_per_asset=usd_per_asset,
            total_usd_balance=thor_to_float(pool.balance_rune) * usd_per_rune * 2.0
        )


@dataclass
class LPDailyGraphPoint:
    timestamp: int = 0
    usd_value: float = 0


LPDailyChartByPoolDict = Dict[str, List[LPDailyGraphPoint]]


@dataclass
class CurrentLiquidity(BaseModelMixin):
    pool: str
    rune_added: float
    asset_added: float
    pool_units: int  # core field. pool units at the moment
    asset_withdrawn: float
    rune_withdrawn: float
    total_added_as_asset: float
    total_added_as_rune: float
    total_added_as_usd: float
    total_withdrawn_as_asset: float
    total_withdrawn_as_rune: float
    total_withdrawn_as_usd: float
    first_add_ts: int
    last_add_ts: int


@dataclass
class FeeReport:
    asset: str = ''
    imp_loss_usd: float = 0.0
    imp_loss_percent: float = 0.0
    fee_usd: float = 0.0
    fee_rune: float = 0.0
    fee_asset: float = 0.0


@dataclass
class ILProtectionReport:
    STATUS_DISABLED = 'disabled'
    STATUS_EARLY = 'early'
    STATUS_FULL = 'full'
    STATUS_PARTIAL = 'partial'
    STATUS_NOT_NEED = 'not_need'

    PROTECTED_STATUSES = (STATUS_FULL, STATUS_PARTIAL)

    @property
    def is_protected(self):
        return self.status in self.PROTECTED_STATUSES

    progress_progress: float = 0.0  # up to 1.0 (full)
    rune_compensation: float = 0.0
    max_rune_compensation: float = 0.0  # if it is 100%
    # cover_of_asset: float = 0.0  # extra amount on withdraw
    # cover_of_rune: float = 0.0  # extra amount on withdraw
    corrected_pool: PoolInfo = field(default_factory=PoolInfo.dummy)
    member_extra_units: int = 0
    status: str = ''


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
class LiquidityPoolReport:
    usd_per_asset: float
    usd_per_rune: float

    usd_per_asset_start: float
    usd_per_rune_start: float

    liq: CurrentLiquidity
    fees: FeeReport
    pool: PoolInfo
    protection: ILProtectionReport

    is_savers: bool = False

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

    def apy_from_change(self, ch):
        return change_ratio_to_apy(ch, self.total_days)

    @property
    def lp_vs_hold(self) -> (float, float):
        rune_added_in_usd = self.liq.rune_added * self.usd_per_rune
        asset_added_in_usd = self.liq.asset_added * self.usd_per_asset
        total_added_in_usd = rune_added_in_usd + asset_added_in_usd

        rune_withdrawn_in_usd = self.liq.rune_withdrawn * self.usd_per_rune
        asset_withdrawn_in_usd = self.liq.asset_withdrawn * self.usd_per_asset
        total_withdrawn_in_usd = rune_withdrawn_in_usd + asset_withdrawn_in_usd

        redeem_rune, redeem_asset = self.redeemable_rune_asset
        redeem_rune_in_usd = redeem_rune * self.usd_per_rune
        redeem_asset_in_usd = redeem_asset * self.usd_per_asset
        total_redeemable_in_usd = redeem_rune_in_usd + redeem_asset_in_usd

        lp_vs_hold_abs = total_redeemable_in_usd + total_withdrawn_in_usd - total_added_in_usd
        lp_vs_hold_percent = lp_vs_hold_abs / total_added_in_usd * 100.0 if total_added_in_usd else 0.0
        return lp_vs_hold_abs, lp_vs_hold_percent

    @property
    def savers_apr(self):
        _, a = self.redeemable_rune_asset
        asset_change = a + self.liq.asset_withdrawn - self.liq.asset_added
        asset_change_r = asset_change / a if a != 0 else 0
        return self.apy_from_change(asset_change_r)

    @property
    def savers_usd_apr(self):
        first_usd_value = self.usd_per_asset_start * self.liq.asset_added
        _, a = self.redeemable_rune_asset
        current_usd_value = a * self.usd_per_asset
        usd_change_r = current_usd_value / first_usd_value - 1.0
        return self.apy_from_change(usd_change_r)

    @property
    def total_days(self):
        total_days = self.total_lping_sec / DAY
        return total_days

    @property
    def lp_vs_hold_apy(self) -> float:
        _, lp_vs_hold_percent = self.lp_vs_hold
        lp_vs_hold_percent /= 100.0
        return self.apy_from_change(lp_vs_hold_percent)

    def gain_loss(self, mode=USD) -> (float, float):
        cur_val = self.current_value(mode)
        wth_val = self.withdrawn_value(mode)
        add_val = self.added_value(mode)

        if not add_val:
            return 0, 0

        gain_loss_abs = cur_val + wth_val - add_val
        gain_loss_percent = gain_loss_abs / add_val * 100.0
        return gain_loss_abs, gain_loss_percent

    @property
    def gain_loss_raw(self):
        redeem_rune, redeem_asset = self.redeemable_rune_asset
        gl_rune = self.liq.rune_withdrawn + redeem_rune - self.liq.rune_added
        gl_asset = self.liq.asset_withdrawn + redeem_asset - self.liq.asset_added
        gl_rune_per = gl_rune / self.liq.rune_added * 100.0 if self.liq.rune_added != 0 else 0.0
        gl_asset_per = gl_asset / self.liq.asset_added * 100.0 if self.liq.asset_added != 0 else 0.0
        return gl_rune, gl_rune_per, gl_asset, gl_asset_per

    @property
    def usd_gain_loss_percent(self):
        gl_rune, gl_rune_per, gl_asset, gl_asset_per = self.gain_loss_raw
        gl_usd = gl_rune * self.usd_per_rune + gl_asset * self.usd_per_asset
        gl_usd_per = gl_usd / self.added_value(self.USD) * 100.0
        return gl_usd_per

    @property
    def redeemable_rune_asset(self):
        if self.is_savers:
            r = 0
            a = self.pool.savers_depth_float / thor_to_float(self.pool.savers_units) * self.liq.pool_units
        else:
            r, a = pool_share(self.pool.balance_rune, self.pool.balance_asset, self.liq.pool_units, self.pool.units)
        return thor_to_float(r), thor_to_float(a)

    def added_value(self, mode):
        if mode == self.USD:
            return self.liq.total_added_as_usd
        elif mode == self.RUNE:
            return self.liq.total_added_as_rune
        elif mode == self.ASSET:
            return self.liq.total_added_as_asset

    def withdrawn_value(self, mode):
        if mode == self.USD:
            return self.liq.total_withdrawn_as_usd
        elif mode == self.RUNE:
            return self.liq.total_withdrawn_as_rune
        elif mode == self.ASSET:
            return self.liq.total_withdrawn_as_asset

    def current_value(self, mode):
        r, a = self.redeemable_rune_asset
        usd_value = r * self.usd_per_rune + a * self.usd_per_asset
        if mode == self.USD:
            return usd_value
        elif mode == self.RUNE:
            return usd_value / self.usd_per_rune
        elif mode == self.ASSET:
            return usd_value / self.usd_per_asset

    @property
    def total_lping_sec(self):
        return int(now_ts()) - self.liq.first_add_ts

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
