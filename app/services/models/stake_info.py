import time
from dataclasses import dataclass, field

from services.lib.datetime import DAY
from services.models.base import BaseModelMixin
from services.models.pool_info import MIDGARD_MULT, PoolInfo

BNB_CHAIN = 'BNB'
BECH_2_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


@dataclass
class MyStakeAddress(BaseModelMixin):
    address: str = ''
    chain: str = BNB_CHAIN
    pools: list = field(default_factory=list)

    @classmethod
    def is_good_address(cls, addr: str, chain=BNB_CHAIN):
        if chain == BNB_CHAIN:
            addr = addr.strip()

            return (addr.startswith('bnb1')
                    and 30 <= len(addr) <= 50
                    and set(addr[4:]) < set(BECH_2_CHARSET))
        else:
            return False


def pool_share(rune_depth, asset_depth, stake_units, pool_unit):
    rune_share = (rune_depth * stake_units) / pool_unit
    asset_share = (asset_depth * stake_units) / pool_unit
    return rune_share, asset_share


@dataclass
class StakeDayGraphPoint:
    asset_depth: int = 0
    rune_depth: int = 0
    busd_rune_price: float = 1.0
    day_str: str = ''
    timestamp: int = 0
    pool_units: int = 0
    stake_units: int = 0

    @classmethod
    def from_asgard(cls, j):
        return cls(
            asset_depth=int(j.get('assetdepth', 1)),
            rune_depth=int(j.get('runedepth', 1)),
            busd_rune_price=float(j.get('busdpricerune', 1.0)),
            day_str=j.get('day', ''),
            pool_units=int(j.get('poolunits', 1)),
            stake_units=int(j.get('stakeunit', 1)),
            timestamp=int(j.get('time', 0)),
        )

    @property
    def usd_value(self):
        r, a = pool_share(self.rune_depth, self.asset_depth, self.stake_units, self.pool_units)
        runes_per_asset = self.rune_depth / self.asset_depth
        total_rune = r * MIDGARD_MULT + a * MIDGARD_MULT * runes_per_asset
        usd_value = total_rune / self.busd_rune_price
        return usd_value


@dataclass
class CurrentLiquidity(BaseModelMixin):
    pool: str
    rune_stake: int
    asset_stake: int
    pool_units: int
    asset_withdrawn: int
    rune_withdrawn: int
    total_staked_asset: int
    total_staked_rune: int
    total_staked_usd: float
    total_unstaked_asset: float
    total_unstaked_rune: float
    total_unstaked_usd: float
    first_stake_ts: int
    last_stake_ts: int

    @classmethod
    def from_asgard(cls, d):
        m = MIDGARD_MULT
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
class StakePoolReport:
    usd_per_asset: float
    usd_per_rune: float

    usd_per_asset_start: float
    usd_per_rune_start: float

    liq: CurrentLiquidity
    pool: PoolInfo

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
        return r * MIDGARD_MULT, a * MIDGARD_MULT

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
