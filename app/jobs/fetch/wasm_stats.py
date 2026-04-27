
from jobs.fetch.cached.rujira_contract_names import RujiraContractNameCache
from jobs.fetch.cached.wasm import WasmCache
from jobs.wasm_recorder import CosmWasmRecorder
from lib.date_utils import now_ts, DAY
from lib.logs import WithLogger
from lib.texts import shorten_text
from models.wasm import WasmPeriodStats, WasmTopContract, WasmDailyPoint


class WasmStatsBuilder(WithLogger):
    """
    Combines WasmCache (deployment metadata) and CosmWasmRecorder (on-chain activity)
    into a single WasmPeriodStats object ready for infographic rendering.

    Usage:
        builder = WasmStatsBuilder(wasm_cache, recorder, last_block_cache)
        stats = await builder.build(days=7, top_n=10)
    """

    def __init__(
        self,
        wasm_cache: WasmCache,
        recorder: CosmWasmRecorder,
        last_block_cache=None,
        contract_name_cache: RujiraContractNameCache = None,
        top_label_limit: int = 32,
    ):
        super().__init__()
        self.wasm_cache = wasm_cache
        self.recorder = recorder
        self.last_block_cache = last_block_cache
        self.contract_name_cache = contract_name_cache
        self.top_label_limit = top_label_limit

    async def build(self, days: float = 7.0, top_n: int = 10) -> WasmPeriodStats:
        now = now_ts()
        period_start = now - days * DAY

        self.logger.info(f"Building WasmPeriodStats for last {days} day(s)...")

        # ----------------------------------------------------------------
        # 1. Deployment snapshot + new deployments
        # ----------------------------------------------------------------
        wasm_stats, new_dep = await self._fetch_deployment_data(days)

        # ----------------------------------------------------------------
        # 2. Activity: current period
        # ----------------------------------------------------------------
        calls_range = await self.recorder.get_calls_range(period_start, now)
        total_calls = sum(
            int(float(d.get(CosmWasmRecorder.KEY_CALLS, 0)))
            for d in calls_range.values()
        )
        current_users, prev_users = await self.recorder.get_current_and_previous_users(int(days))

        # ----------------------------------------------------------------
        # 3. Activity: previous period total calls
        # ----------------------------------------------------------------
        prev_start = period_start - days * DAY
        prev_calls_range = await self.recorder.get_calls_range(prev_start, period_start)
        prev_total_calls = sum(
            int(float(d.get(CosmWasmRecorder.KEY_CALLS, 0)))
            for d in prev_calls_range.values()
        )

        # ----------------------------------------------------------------
        # 4. Top contracts
        # ----------------------------------------------------------------
        top_contracts = await self._build_top_contracts(period_start, now, top_n, int(days))

        # ----------------------------------------------------------------
        # 5. Daily chart
        # ----------------------------------------------------------------
        daily_chart = await self._build_daily_chart(calls_range, period_start, now)

        stats = WasmPeriodStats(
            days=days,
            period_start_ts=period_start,
            period_end_ts=now,
            total_codes=wasm_stats.total_codes,
            total_contracts=wasm_stats.total_contracts,
            new_codes=new_dep.new_codes_count,
            new_contracts=new_dep.new_contracts_count,
            total_calls=total_calls,
            unique_users=current_users,
            prev_total_calls=prev_total_calls,
            prev_unique_users=prev_users,
            top_contracts=top_contracts,
            daily_chart=daily_chart,
        )
        self.logger.info(f"WasmPeriodStats built: {stats}")
        return stats

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_deployment_data(self, days: float):
        wasm_stats = await self.wasm_cache.get()
        new_dep = await self.wasm_cache.count_new_deployments(
            days=days,
            last_block_cache=self.last_block_cache,
        )
        return wasm_stats, new_dep

    async def _build_top_contracts(
        self,
        period_start: float,
        now: float,
        top_n: int,
        days: int,
    ):
        totals = await self.recorder.get_all_contracts_calls_totals(period_start, now)
        # Sort descending by call count, take top_n
        ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:top_n]

        top_contracts = []
        for addr, calls in ranked:
            label = await self.wasm_cache.get_label(addr)
            display_label = await self._resolve_display_label(addr, label)
            unique_users = await self.recorder.get_contract_unique_users(addr, days=days)
            top_contracts.append(WasmTopContract(
                address=addr,
                label=label,
                calls=calls,
                unique_users=unique_users,
                display_label=display_label,
            ))
            self.logger.debug(
                f"  top contract: calls={calls:>6}  users={unique_users:>5}"
                f"  label={label!r}  display={display_label!r}  {addr}"
            )
        return top_contracts

    async def _resolve_display_label(self, address: str, label: str) -> str:
        friendly_label = label

        if self.contract_name_cache is not None:
            try:
                friendly_label = await self.contract_name_cache.resolve_name(address, fallback=label)
            except Exception as exc:
                self.logger.warning(f'Could not resolve friendly contract name for {address}: {exc}')

        friendly_label = friendly_label or label or 'Unlabeled contract'
        return shorten_text(friendly_label, self.top_label_limit, end='…')

    async def _build_daily_chart(
        self,
        calls_range: dict,
        period_start: float,
        now: float,
    ):
        users_range = await self.recorder.get_users_range(period_start, now)

        chart = []
        for ts, day_data in sorted(calls_range.items()):
            day_calls = int(float(day_data.get(CosmWasmRecorder.KEY_CALLS, 0)))
            day_users = users_range.get(ts, 0)
            chart.append(WasmDailyPoint(ts=ts, calls=day_calls, unique_users=day_users))

        self.logger.debug(f"Daily chart: {len(chart)} point(s).")
        return chart

