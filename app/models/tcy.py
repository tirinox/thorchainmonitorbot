from typing import Dict

from pydantic import BaseModel

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


class TcyMimirs:
    HALT_TRADING = 'HALTTCYTRADING'
    HALT_CLAIMING = 'TCYCLAIMINGHALT'
    HALT_CLAIMING_SWAP = 'TCYCLAIMINGSWAPHALT'
    HALT_STAKE_DISTRIBUTION = 'TCYSTAKEDISTRIBUTIONHALT'
    HALT_STAKING = 'TCYSTAKINGHALT'
    HALT_UNSTAKING = 'TCYUNSTAKINGHALT'


class TcyFullInfo(BaseModel):
    vnx: VNXTcyData
    status: TcyStatus

    # todo: add earnings, previous
