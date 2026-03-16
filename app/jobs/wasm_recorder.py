from typing import Optional, Dict

from jobs.scanner.block_result import BlockResult
from jobs.scanner.wasm_execute import CosmwasmExecuteDecoder
from lib.accumulator import DailyAccumulator
from lib.active_users import DailyActiveUserCounter
from lib.date_utils import now_ts
from lib.db import DB
from lib.delegates import INotified
from lib.logs import WithLogger


class CosmWasmRecorder(INotified, WithLogger):
    """
    Listens to BlockResult events, uses CosmwasmExecuteDecoder to identify
    CosmWasm MsgExecuteContract calls and records daily statistics:

    - total call count        (DailyAccumulator, field='calls')
    - unique callers per day  (DailyActiveUserCounter backed by Redis HyperLogLog)
    - per-contract call count (DailyAccumulator, one field per contract address)
    - per-contract unique callers (DailyActiveUserCounter, lazily created per address)

    Wire into the block-scanner pipeline as a subscriber of BlockScanner:
        block_scanner.add_subscriber(wasm_recorder)
    """

    KEY_CALLS = 'calls'
    ACCUM_NAME_CALLS = 'CosmWasm:DailyCalls'
    ACCUM_NAME_CONTRACTS = 'CosmWasm:ContractCalls'
    USER_COUNTER_NAME = 'CosmWasmUsers'
    CONTRACT_USER_COUNTER_PREFIX = 'CosmWasmUsers:c'

    def __init__(self, db: DB):
        super().__init__()
        self._db = db
        self._decoder = CosmwasmExecuteDecoder()
        self._call_accum = DailyAccumulator(self.ACCUM_NAME_CALLS, db)
        self._contract_accum = DailyAccumulator(self.ACCUM_NAME_CONTRACTS, db)
        self._user_counter = DailyActiveUserCounter(db.redis, self.USER_COUNTER_NAME)
        # Per-contract unique-user counters, lazily created
        self._contract_user_counters: Dict[str, DailyActiveUserCounter] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_contract_user_counter(self, contract_address: str) -> DailyActiveUserCounter:
        if contract_address not in self._contract_user_counters:
            self._contract_user_counters[contract_address] = DailyActiveUserCounter(
                self._db.redis,
                f'{self.CONTRACT_USER_COUNTER_PREFIX}:{contract_address}',
            )
        return self._contract_user_counters[contract_address]

    # ------------------------------------------------------------------
    # Core recording logic
    # ------------------------------------------------------------------

    async def on_data(self, sender, data: BlockResult):
        # Use the block's own timestamp so historical replays land in the correct daily bucket.
        now = float(data.timestamp) if data.timestamp else now_ts()

        for tx in data.txs:
            matched_contracts = [
                message.contract_address
                for message in tx.messages
                if message.is_contract and message.contract_address
            ]

            if not matched_contracts:
                continue

            await self._call_accum.add(now, **{self.KEY_CALLS: 1})

            user = tx.first_signer_address
            if user:
                await self._user_counter.hit(user=user, now=now)

            for contract_addr in matched_contracts:
                await self._contract_accum.add(now, **{contract_addr: 1})
                if user:
                    await self._get_contract_user_counter(contract_addr).hit(user=user, now=now)

            self.logger.debug(
                f'Block #{data.block_no}: tx={tx.tx_hash[:8]}... '
                f'user={user} contracts={matched_contracts}'
            )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def get_daily_calls(self, ts: Optional[float] = None) -> int:
        """Total number of CosmWasm execute TXs for the day containing *ts*."""
        data = await self._call_accum.get(ts or now_ts())
        return int(float(data.get(self.KEY_CALLS, 0)))

    async def get_daily_unique_users(self, ts: Optional[float] = None) -> int:
        """Approximate unique callers (HyperLogLog) for the day containing *ts*."""
        return await self._user_counter.get_dau(ts or now_ts())

    async def get_unique_users_over_days(self, days: int = 7) -> int:
        """Approximate unique callers across the last *days* calendar days."""
        return await self._user_counter.get_au_over_days(days)

    async def get_current_and_previous_users(self, days: int = 7):
        """Return (current_period_users, previous_period_users) for *days*-day windows."""
        return await self._user_counter.get_current_and_previous_au(days)

    async def get_daily_contract_calls(
        self,
        contract_address: str,
        ts: Optional[float] = None,
    ) -> int:
        """Number of MsgExecuteContract calls to *contract_address* on the given day."""
        data = await self._contract_accum.get(ts or now_ts())
        return int(float(data.get(contract_address, 0)))

    async def get_all_daily_contract_calls(self, ts: Optional[float] = None) -> dict:
        """
        Returns {contract_address: call_count} for every contract called
        on the day containing *ts*.
        """
        data = await self._contract_accum.get(ts or now_ts())
        return {k: int(float(v)) for k, v in data.items()}

    async def get_calls_range(
        self,
        start_ts: float,
        end_ts: Optional[float] = None,
    ) -> dict:
        """Total-call counts keyed by bucket timestamp over [start_ts, end_ts]."""
        return await self._call_accum.get_range(start_ts, end_ts)

    async def get_contract_calls_range(
        self,
        contract_address: str,
        start_ts: float,
        end_ts: Optional[float] = None,
    ) -> dict:
        """
        Returns {bucket_ts: call_count} for *contract_address*
        over the range [start_ts, end_ts].
        """
        raw = await self._contract_accum.get_range(start_ts, end_ts)
        return {
            ts: int(float(d.get(contract_address, 0)))
            for ts, d in raw.items()
        }

    async def get_all_contracts_calls_totals(
        self,
        start_ts: float,
        end_ts: Optional[float] = None,
    ) -> Dict[str, int]:
        """
        Returns {contract_address: total_calls} summed across all days in [start_ts, end_ts].
        Excludes the internal KEY_CALLS sentinel if it somehow ends up there.
        """
        raw = await self._contract_accum.get_range(start_ts, end_ts)
        totals: Dict[str, int] = {}
        for day_data in raw.values():
            for addr, count in day_data.items():
                totals[addr] = totals.get(addr, 0) + int(float(count))
        return totals

    async def get_users_range(
        self,
        start_ts: float,
        end_ts: Optional[float] = None,
    ) -> Dict[float, int]:
        """
        Returns {bucket_ts: unique_users} aligned with the daily calls buckets,
        using HyperLogLog pfcount per day.
        """
        calls_data = await self._call_accum.get_range(start_ts, end_ts)
        result: Dict[float, int] = {}
        for ts in calls_data:
            result[ts] = await self._user_counter.get_dau(ts)
        return result

    async def get_contract_unique_users(
        self,
        contract_address: str,
        days: int = 7,
        start: int = 0,
    ) -> int:
        """
        Approximate unique callers for *contract_address* over *days* days
        starting *start* days ago (0 = current period, days = previous period).
        """
        counter = self._get_contract_user_counter(contract_address)
        return await counter.get_au_over_days(days, start=start)


