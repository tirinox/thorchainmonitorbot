import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Callable, Awaitable

from api.aionode.connector import ThorConnector
from jobs.fetch.base import BaseFetcher
from lib.constants import thor_to_float, THOR_BLOCK_TIME, POL_RESERVE_MODULE, ADR24_FIRST_DEPLOY_BLOCK
from lib.date_utils import DAY, HOUR, now_ts, date_parse_rfc
from lib.depcont import DepContainer
from lib.utils import safe_get
from models.earnings_history import EarningsInterval
from models.mimir_naming import MIMIR_KEY_POL_RESERVE_SYSTEM_INCOME_BPS, MIMIR_KEY_POL_RESERVE_MAX_DEPLOYMENT
from models.pol_reserve import PolReserveSnapshot, PolReservePoolSnapshot, PolReserveDay, AlertPolReserveStats, \
    build_pol_reserve_day


def utc_date_str(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')


async def find_height_at_timestamp(
        target_ts: float,
        hint_height: int,
        hint_ts: float,
        get_block_ts: Callable[[int], Awaitable[float]],
        max_height: int = 0,
        tolerance: float = THOR_BLOCK_TIME * 2,
        max_steps: int = 16,
) -> int:
    """
    Finds a block produced at target_ts or a little earlier (within the tolerance).
    Starts from a known block (the hint) and corrects the guess by the timestamps of the blocks it lands on,
    learning the real block time on the way.
    """
    block_time = THOR_BLOCK_TIME
    known_height, known_ts = hint_height, hint_ts
    height = hint_height - round((hint_ts - target_ts) / block_time)
    for _ in range(max_steps):
        height = max(1, height)
        if max_height:
            height = min(max_height, height)

        ts = await get_block_ts(height)
        diff = target_ts - ts
        if 0 <= diff < tolerance:
            return height

        if height != known_height and (measured := (known_ts - ts) / (known_height - height)) > 0:
            block_time = measured
        known_height, known_ts = height, ts

        step = int(diff / block_time)
        if not step:
            step = 1 if diff > 0 else -1
        if (height == 1 and step < 0) or (max_height and height == max_height and step > 0):
            return height
        height += step

    raise LookupError(f'No block found at timestamp {target_ts} in {max_steps} steps')


class PolReserveFetcher(BaseFetcher):
    """
    Collects the state of the system income funded POL (ADR-024, the pol_reserve module):
    the current positions and their day by day history.
    The history is read from the state of the node at the last block of every UTC day, no block scanning is needed.
    """

    DB_KEY_DAY_END = 'POLReserve:DayEnd:v1'
    MAX_CONCURRENT_DAYS = 4

    # The whole history is loaded: the USD cost of the deposits and the total fees are sums over all the days.
    # Midgard gives 400 intervals at most. Once POL is older than that, those sums will cover only the last year.
    MAX_DAYS = 366

    def __init__(self, deps: DepContainer, days: int = MAX_DAYS):
        super().__init__(deps, sleep_period=HOUR)
        self.days = days
        self._module_address = ''

    @property
    def archive_connector(self) -> ThorConnector:
        return self.deps.thor_connector_archive or self.deps.thor_connector

    # ---- Snapshots ----

    async def get_module_address(self) -> str:
        if not self._module_address:
            balance = await self.deps.thor_connector.query_module_balance(POL_RESERVE_MODULE)
            if not balance or not balance.address:
                raise ConnectionError(f'Failed to load the {POL_RESERVE_MODULE} module address')
            self._module_address = balance.address
        return self._module_address

    async def load_snapshot(self, height: int = 0, timestamp: float = 0,
                            connector: Optional[ThorConnector] = None) -> PolReserveSnapshot:
        connector = connector or (self.archive_connector if height else self.deps.thor_connector)
        address = await self.get_module_address()

        pools = await connector.query_pools(height or None)
        if not pools:
            raise ConnectionError(f'Failed to load pools at height {height or "latest"}')
        pools = [p for p in pools if p.pol_reserve_rune_deposited > 0]

        members = await asyncio.gather(*(
            connector.query_liquidity_provider(p.asset, address, height or None) for p in pools
        ))

        positions = []
        for pool, member in zip(pools, members):
            if not member or not member.units:
                # RUNE has been deployed to this pool, so the module must be its member. Do not trust this answer.
                raise ConnectionError(f'Failed to load the POL position in {pool.asset} at height {height or "latest"}')
            positions.append(PolReservePoolSnapshot(
                asset=pool.asset,
                rune_deposited=pool.pol_reserve_rune_deposited,
                units=member.units,
                pool_units=pool.pool_units,
                balance_rune=pool.balance_rune,
                balance_asset=pool.balance_asset,
                status=pool.status,
            ))
        positions.sort(key=lambda p: p.rune_deposited, reverse=True)

        return PolReserveSnapshot(height=int(height), timestamp=int(timestamp), pools=positions)

    async def load_current_snapshot(self) -> PolReserveSnapshot:
        height = await self.deps.last_block_cache.get_thor_block()
        if not height:
            raise ConnectionError('Failed to load the last block height')

        snapshot = await self.load_snapshot(timestamp=now_ts())
        snapshot.height = int(height)
        snapshot.usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()

        balance = await self.deps.thor_connector.query_module_balance(POL_RESERVE_MODULE)
        snapshot.undeployed_rune = balance.runes if balance else 0
        return snapshot

    # ---- History ----

    async def get_block_timestamp(self, height: int) -> float:
        raw = await self.archive_connector.query_tendermint_block_raw(height)
        time_str = safe_get(raw, 'result', 'block', 'header', 'time') or safe_get(raw, 'block', 'header', 'time')
        if not time_str:
            raise ConnectionError(f'Failed to load the timestamp of block {height}')
        return date_parse_rfc(time_str).replace(tzinfo=timezone.utc).timestamp()

    async def _load_cached_day_end(self, date: str) -> Optional[PolReserveSnapshot]:
        r = await self.deps.db.get_redis()
        raw = await r.hget(self.DB_KEY_DAY_END, date)
        if raw:
            try:
                return PolReserveSnapshot.from_json(json.loads(raw))
            except (ValueError, TypeError) as e:
                self.logger.warning(f'Bad cached POL reserve snapshot for {date}: {e!r}')

    async def _save_day_end(self, date: str, snapshot: PolReserveSnapshot):
        r = await self.deps.db.get_redis()
        await r.hset(self.DB_KEY_DAY_END, date, json.dumps(snapshot.to_dict()))

    async def load_day_end_snapshots(self, current: PolReserveSnapshot, days: int) -> Dict[str, PolReserveSnapshot]:
        """
        Returns the snapshots at the last block of the given number of complete UTC days, keyed by the date.
        A finished day never changes, so its snapshot is loaded once and then kept in the DB.
        Days before the first POL reserve deployment are left out.
        """
        today_start = int(current.timestamp // DAY * DAY)
        results: Dict[str, PolReserveSnapshot] = {}
        to_load = []  # (date, boundary timestamp, height)

        # from the newest day to the oldest one, so every found block is a close hint for the next search
        hint_height, hint_ts = current.height, current.timestamp
        for days_ago in range(1, days + 1):
            day_start = today_start - days_ago * DAY
            boundary_ts = day_start + DAY
            date = utc_date_str(day_start)

            if cached := await self._load_cached_day_end(date):
                results[date] = cached
                hint_height, hint_ts = cached.height, boundary_ts
                continue

            estimated = hint_height - (hint_ts - boundary_ts) / THOR_BLOCK_TIME
            if estimated < ADR24_FIRST_DEPLOY_BLOCK - DAY / THOR_BLOCK_TIME:
                break  # way before the activation, no need to look further

            height = await find_height_at_timestamp(
                boundary_ts, hint_height, hint_ts, self.get_block_timestamp, max_height=current.height
            )
            hint_height, hint_ts = height, boundary_ts
            if height < ADR24_FIRST_DEPLOY_BLOCK:
                break
            to_load.append((date, boundary_ts, height))

        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_DAYS)

        async def load(date, boundary_ts, height):
            async with semaphore:
                snapshot = await self.load_snapshot(height, boundary_ts)
                await self._save_day_end(date, snapshot)
                results[date] = snapshot

        if to_load:
            self.logger.info(f'Loading {len(to_load)} day end snapshots of the POL reserve')
            await asyncio.gather(*(load(*item) for item in to_load))

        return results

    async def load_earnings_by_date(self, days: int) -> Dict[str, EarningsInterval]:
        try:
            earnings = await self.deps.midgard_connector.query_earnings(count=days + 1, interval='day')
        except Exception as e:
            self.logger.warning(f'Failed to load earnings history: {e!r}')
            earnings = None
        if not earnings:
            self.logger.warning('No earnings history: fees and historical prices will be missing')
            return {}
        return {utc_date_str(interval.start_time): interval for interval in earnings.intervals}

    @staticmethod
    def _make_day(date: str, start: Optional[PolReserveSnapshot], end: PolReserveSnapshot,
                  cumulative_before: float, interval: Optional[EarningsInterval],
                  fallback_usd_per_rune: float = 0.0, partial: bool = False) -> PolReserveDay:
        day_start = int(datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
        pools = interval.pools if interval else []
        return build_pol_reserve_day(
            date, day_start, start, end,
            cumulative_before=cumulative_before,
            usd_per_rune=(interval.rune_price_usd if interval else 0.0) or fallback_usd_per_rune,
            system_income_rune=thor_to_float(interval.earnings) if interval else 0.0,
            pool_fees_rune={p.pool: thor_to_float(p.total_liquidity_fees_rune) for p in pools},
            pool_earnings_rune={p.pool: thor_to_float(p.earnings) for p in pools},
            partial=partial,
        )

    async def load_days(self, current: PolReserveSnapshot, days: int) -> List[PolReserveDay]:
        # one more day is needed as the starting point of the first day
        day_ends, earnings = await asyncio.gather(
            self.load_day_end_snapshots(current, days + 1),
            self.load_earnings_by_date(days + 1),
        )

        result = []
        dates = sorted(day_ends.keys())
        previous = None
        if len(dates) > days:
            previous = day_ends[dates[0]]
            dates = dates[1:]

        for date in dates:
            end = day_ends[date]
            result.append(self._make_day(
                date, previous, end,
                cumulative_before=previous.rune_deposited if previous else 0.0,
                interval=earnings.get(date),
            ))
            previous = end

        # Midgard reports the unfinished day as zeros with a stale price: fees of today are not known yet
        result.append(self._make_day(
            utc_date_str(current.timestamp), previous, current,
            cumulative_before=previous.rune_deposited if previous else 0.0,
            interval=None,
            fallback_usd_per_rune=current.usd_per_rune,
            partial=True,
        ))
        return result

    async def fetch(self) -> AlertPolReserveStats:
        mimir = await self.deps.mimir_cache.get_mimir_holder()
        system_income_bps = mimir.get_constant(MIMIR_KEY_POL_RESERVE_SYSTEM_INCOME_BPS, 0)
        max_deployment = thor_to_float(mimir.get_constant(MIMIR_KEY_POL_RESERVE_MAX_DEPLOYMENT, 0))

        current = await self.load_current_snapshot()
        days = await self.load_days(current, self.days)

        return AlertPolReserveStats(
            current=current,
            days=days,
            system_income_bps=int(system_income_bps),
            max_deployment_rune=max_deployment,
            module_address=await self.get_module_address(),
        )
