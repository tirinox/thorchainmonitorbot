import dataclasses
from typing import NamedTuple, List

from lib.constants import thor_to_float


class PoolEarnings(NamedTuple):
    asset_liquidity_fees: int
    earnings: int
    pool: str
    rewards: int
    rune_liquidity_fees: int
    saver_earning: int
    total_liquidity_fees_rune: int

    @classmethod
    def from_dict(cls, data: dict) -> 'PoolEarnings':
        return cls(
            asset_liquidity_fees=int(data['assetLiquidityFees']),
            earnings=int(data['earnings']),
            pool=data['pool'],
            rewards=int(data['rewards']),
            rune_liquidity_fees=int(data['runeLiquidityFees']),
            saver_earning=int(data['saverEarning']),
            total_liquidity_fees_rune=int(data['totalLiquidityFeesRune'])
        )


class EarningsInterval(NamedTuple):
    avg_node_count: float
    block_rewards: int
    bonding_earnings: int
    earnings: int
    end_time: int
    liquidity_earnings: int
    liquidity_fees: int
    pools: List[PoolEarnings]
    rune_price_usd: float
    start_time: int

    @staticmethod
    def from_dict(data: dict) -> 'EarningsInterval':
        return EarningsInterval(
            avg_node_count=float(data['avgNodeCount']),
            block_rewards=int(data['blockRewards']),
            bonding_earnings=int(data['bondingEarnings']),
            earnings=int(data['earnings']),
            end_time=int(data['endTime']),
            liquidity_earnings=int(data['liquidityEarnings']),
            liquidity_fees=int(data['liquidityFees']),
            pools=[PoolEarnings.from_dict(pool) for pool in data['pools']],
            rune_price_usd=float(data['runePriceUSD']),
            start_time=int(data['startTime'])
        )

    def find_pool(self, pool_name: str) -> PoolEarnings | None:
        for pool in self.pools:
            if pool.pool == pool_name:
                return pool
        return None


@dataclasses.dataclass
class EarningsTuple:
    total_earnings: float
    block_earnings: float
    liquidity_earnings: float
    liquidity_fees: float
    bonding_earnings: float
    affiliate_revenue: float = 0.0


class EarningHistoryResponse(NamedTuple):
    intervals: List[EarningsInterval]
    meta: EarningsInterval

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            intervals=[EarningsInterval.from_dict(interval) for interval in data['intervals']],
            meta=EarningsInterval.from_dict(data['meta'])
        )

    @staticmethod
    def calc_earnings(intervals: List[EarningsInterval]):
        """
            earning = bondingEarnings + liquidityEarnings
        """

        total_earnings = sum(thor_to_float(e.earnings) * e.rune_price_usd for e in intervals)
        block_earnings = sum(thor_to_float(e.block_rewards) * e.rune_price_usd for e in intervals)
        liquidity_fees = sum(thor_to_float(e.liquidity_fees) * e.rune_price_usd for e in intervals)
        liquidity_earnings = sum(thor_to_float(e.liquidity_earnings) for e in intervals)
        bonding_earnings = sum(thor_to_float(e.bonding_earnings) * e.rune_price_usd for e in intervals)
        return EarningsTuple(
            total_earnings=total_earnings,
            block_earnings=block_earnings,
            liquidity_earnings=liquidity_earnings,
            liquidity_fees=liquidity_fees,
            bonding_earnings=bonding_earnings,
            affiliate_revenue=0,
        )
