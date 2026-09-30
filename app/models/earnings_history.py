import dataclasses
from typing import NamedTuple, List, Optional

from lib.constants import thor_to_float
from lib.date_utils import HOUR

# Rows of the "pools" array of Midgard earnings that are not pools but system income categories
EARNINGS_POOL_DEV_FUND = 'dev_fund_reward'
EARNINGS_POOL_MARKETING_FUND = 'marketing_fund_reward'
EARNINGS_POOL_INCOME_BURN = 'income_burn'
EARNINGS_POOL_TCY_STAKE = 'tcy_stake_reward'
EARNINGS_POOL_POL_RESERVE = 'pol_reserve_reward'


def is_real_pool_name(name: str) -> bool:
    # every real pool is CHAIN.ASSET; system income categories have no dot
    return '.' in name


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
        liquidity_earnings = sum(thor_to_float(e.liquidity_earnings) * e.rune_price_usd for e in intervals)
        bonding_earnings = sum(thor_to_float(e.bonding_earnings) * e.rune_price_usd for e in intervals)
        return EarningsTuple(
            total_earnings=total_earnings,
            block_earnings=block_earnings,
            liquidity_earnings=liquidity_earnings,
            liquidity_fees=liquidity_fees,
            bonding_earnings=bonding_earnings,
            affiliate_revenue=0,
        )


class IncomeCategory:
    NODES = 'nodes'
    POOLS = 'pools'
    POL_RESERVE = 'pol_reserve'
    TCY = 'tcy'
    DEV_FUND = 'dev_fund'
    MARKETING = 'marketing'
    BURN = 'burn'
    OTHER = 'other'

    # display order: nodes and pools share what the Incentive Pendulum leaves them, the rest are fixed by Mimir;
    # OTHER is appended only when Midgard reports a category we do not know
    ORDER = (NODES, POOLS, POL_RESERVE, TCY, DEV_FUND, MARKETING, BURN)

    BY_EARNINGS_POOL = {
        EARNINGS_POOL_POL_RESERVE: POL_RESERVE,
        EARNINGS_POOL_TCY_STAKE: TCY,
        EARNINGS_POOL_DEV_FUND: DEV_FUND,
        EARNINGS_POOL_MARKETING_FUND: MARKETING,
        EARNINGS_POOL_INCOME_BURN: BURN,
    }


@dataclasses.dataclass
class IncomeCategoryAmount:
    key: str
    rune_raw: int = 0  # accrued, in base units (1e-8 Rune)
    usd: float = 0.0  # every interval is converted at its own Rune price
    share: float = 0.0  # of the distributed USD total, 0..1

    @property
    def rune(self) -> float:
        return thor_to_float(self.rune_raw)


@dataclasses.dataclass
class IncomeDistribution:
    """
    What the system income of a period was actually accrued to, category by category.
    It is summed from Midgard earnings intervals, so it follows the shares that were in force in each of them.
    "Accrued" is not "paid out": node rewards and TCY distributions reach the wallets later.
    """
    start_ts: int
    end_ts: int
    categories: List[IncomeCategoryAmount]
    total_rune_raw: int = 0  # Midgard "earnings": what was distributed
    total_usd: float = 0.0
    liquidity_fees_rune_raw: int = 0  # sources of the income
    block_rewards_rune_raw: int = 0
    discrepancy_rune_raw: int = 0  # total minus the sum of the categories; it is reported, never normalised away
    issues: List[str] = dataclasses.field(default_factory=list)
    prev_total_usd: Optional[float] = None  # the period before; stays None when it has gaps

    @property
    def total_rune(self) -> float:
        return thor_to_float(self.total_rune_raw)

    @property
    def is_complete(self) -> bool:
        return not self.issues

    def find(self, key: str) -> Optional[IncomeCategoryAmount]:
        return next((c for c in self.categories if c.key == key), None)


def build_income_distribution(intervals: List[EarningsInterval], start_ts: int, end_ts: int,
                              interval_sec: int = HOUR) -> IncomeDistribution:
    """
    Sums earnings intervals that must cover [start_ts, end_ts) without gaps.
    Anything that makes the coverage doubtful goes to "issues": an empty interval is not a proof of zero income.
    """
    rune = {key: 0 for key in IncomeCategory.ORDER}
    usd = {key: 0.0 for key in IncomeCategory.ORDER}
    issues = []
    total_raw = fees_raw = block_rewards_raw = 0
    total_usd = 0.0

    def add(key, amount_raw, price):
        rune[key] = rune.get(key, 0) + amount_raw
        usd[key] = usd.get(key, 0.0) + thor_to_float(amount_raw) * price

    expected_start = start_ts
    empty_count = 0
    for interval in intervals:
        if interval.start_time != expected_start:
            issues.append(f'gap or overlap at {expected_start}: interval starts at {interval.start_time}')
        if interval.end_time - interval.start_time != interval_sec:
            issues.append(f'interval at {interval.start_time} is not {interval_sec} sec long')
        expected_start = interval.end_time

        if not interval.earnings:
            empty_count += 1

        price = interval.rune_price_usd
        total_raw += interval.earnings
        total_usd += thor_to_float(interval.earnings) * price
        fees_raw += interval.liquidity_fees
        block_rewards_raw += interval.block_rewards

        add(IncomeCategory.NODES, interval.bonding_earnings, price)
        for pool in interval.pools:
            # "earnings" of a pool is its final income (fees + rewards, the latter is often negative);
            # for the special rows it equals "rewards", so they must not be added together
            if is_real_pool_name(pool.pool):
                add(IncomeCategory.POOLS, pool.earnings, price)
            else:
                add(IncomeCategory.BY_EARNINGS_POOL.get(pool.pool, IncomeCategory.OTHER), pool.earnings, price)

    if not intervals:
        issues.append('no intervals')
    elif expected_start != end_ts:
        issues.append(f'intervals end at {expected_start}, expected {end_ts}')
    if empty_count:
        issues.append(f'{empty_count} empty interval(s)')

    keys = list(IncomeCategory.ORDER)
    if IncomeCategory.OTHER in rune:
        keys.append(IncomeCategory.OTHER)

    return IncomeDistribution(
        start_ts=start_ts,
        end_ts=end_ts,
        categories=[
            IncomeCategoryAmount(key, rune[key], usd[key], share=usd[key] / total_usd if total_usd else 0.0)
            for key in keys
        ],
        total_rune_raw=total_raw,
        total_usd=total_usd,
        liquidity_fees_rune_raw=fees_raw,
        block_rewards_rune_raw=block_rewards_raw,
        discrepancy_rune_raw=total_raw - sum(rune.values()),
        issues=issues,
    )
