from typing import Dict, List

from pydantic import BaseModel, computed_field

from lib.constants import thor_to_float
from .base import IntFromStr


class TcyStaker(BaseModel):
    address: str
    amount: IntFromStr


class VNXTcyUnclaimInfo(BaseModel):
    total: int
    count: int
    assets: Dict[str, int]


class VNXTcyStakerInfo(BaseModel):
    total: int
    count: int


class VNXTcyClaimedInfo(BaseModel):
    count: int
    total: int


class VNXTcyData(BaseModel):
    unclaim_info: VNXTcyUnclaimInfo
    staker_info: VNXTcyStakerInfo

    pending_reward: int
    unclaimed: int
    claimed_not_staked: int
    treasury: int
    tcy_in_pool: int

    claimed_info: VNXTcyClaimedInfo

    price: float
    TCYSupply: int
    runeSupply: int
    pol_tcy: int
    last_week_earnings: int
    tcy_stake_eod: int

    # string fields that should be parsed into int
    tcy_pool_eod: IntFromStr
    total_tcy_locked: IntFromStr
    total_tcy_locked_usd: IntFromStr
    stcy_minted: IntFromStr
    tcy_account_bond: IntFromStr


class TcyStatus(BaseModel):
    halt_trading: bool
    halt_claiming: bool
    halt_claiming_swap: bool
    halt_stake_distribution: bool
    halt_staking: bool
    halt_unstaking: bool
    system_income_bps_to_tcy: int


class TcyMimirs:
    HALT_TRADING = 'HALTTCYTRADING'
    HALT_CLAIMING = 'TCYCLAIMINGHALT'
    HALT_CLAIMING_SWAP = 'TCYCLAIMINGSWAPHALT'
    HALT_STAKE_DISTRIBUTION = 'TCYSTAKEDISTRIBUTIONHALT'
    HALT_STAKING = 'TCYSTAKINGHALT'
    HALT_UNSTAKING = 'TCYUNSTAKINGHALT'

    MIN_RUNE_STAKE_DISTRIBUTION = 'MinRuneForTCYStakeDistribution'.upper()
    MIN_TCY_STAKE_DISTRIBUTION = 'MinTCYForTCYStakeDistribution'.upper()
    TCY_STAKE_SYSTEM_INCOME_BPS = 'TCYStakeSystemIncomeBps'.upper()


class TcyEarningsPoint(BaseModel):
    timestamp: int
    day_no: int
    stake_rune: float
    stake_usd: float
    pool_rune: float
    pool_usd: float
    tcy_price: float


class TcyFullInfo(BaseModel):
    vnx: VNXTcyData
    status: TcyStatus
    tcy_total_supply: int
    usd_per_tcy: float
    usd_per_rune: float
    rune_market_cap_usd: float

    earnings: List[TcyEarningsPoint]

    @computed_field
    @property
    def market_cap(self) -> float:
        return self.tcy_total_supply * self.usd_per_tcy

    @computed_field
    @property
    def percent_of_rune_market_cap(self) -> float:
        if self.rune_market_cap_usd == 0:
            return 0.0
        return 100.0 * self.market_cap / self.rune_market_cap_usd

    @computed_field
    @property
    def tcy_staked(self) -> float:
        return thor_to_float(self.vnx.staker_info.total)

    def get_apr(self, points):
        number_of_days = len(points)
        usd_total_earnings = sum(p.stake_usd for p in points)
        staked_usd = self.tcy_staked * self.usd_per_tcy
        if staked_usd == 0 or number_of_days == 0:
            return 0.0
        daily_earnings = usd_total_earnings / number_of_days
        apr = (daily_earnings * 365 / staked_usd) * 100.0
        return apr

    @computed_field
    @property
    def apr_current(self) -> float:
        total_days = len(self.earnings)
        middle_days = total_days // 2
        return self.get_apr(self.earnings[middle_days:total_days])
