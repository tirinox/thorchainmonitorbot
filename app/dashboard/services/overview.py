import asyncio
import dataclasses

from dashboard.context import DashboardContext
from jobs.fetch.base import DataController
from jobs.scanner.scanner_state import ScannerStateDB
from jobs.transfer_recorder import RuneTransferRecorder
from lib.date_utils import now_ts
from models.transfer import AlertRuneTransferStats
from notify.pub_configure import PublicAlertJobExecutor


async def dedup_info(ctx: DashboardContext) -> list[dict]:
    async def one(name, dedup):
        bit_count, size, stats = await asyncio.gather(dedup.bit_count(), dedup.length(), dedup.load_stats())
        return {
            'name': name,
            'bits_set': bit_count,
            'size': size,
            'total_reads': stats['total_requests'],
            'positive': stats['positive_requests'],
            'writes': stats['write_requests'],
        }

    return list(await asyncio.gather(*(one(name, dedup) for name, dedup in ctx.deduplicators.items())))


async def fetchers_info(ctx: DashboardContext) -> dict:
    data = await DataController().load_stats(ctx.deps.db) or {}
    return {
        'now': now_ts(),
        'all_paused': bool(data.get('all_paused', False)),
        'trackers': data.get('trackers', []),
    }


async def curve_info(ctx: DashboardContext) -> list[dict]:
    ph = await ctx.deps.pool_cache.get()
    return (
            ctx.swap_notifier.dbg_evaluate_curve_for_pools(ph, silent=True) +
            ctx.liquidity_notifier.dbg_evaluate_curve_for_pools(ph, silent=True)
    )


async def user_stats(ctx: DashboardContext) -> dict:
    sm = ctx.deps.settings_manager
    users = await sm.all_users_having_settings()
    return {
        'user_settings_count': len(users),
        'bot_user_count': await sm.bot_user_count(),
    }


async def rune_transfer_stats(ctx: DashboardContext) -> dict:
    d = ctx.deps
    recorder = RuneTransferRecorder(d)
    summary = await recorder.get_summary(days=PublicAlertJobExecutor.RUNE_TRANSFER_STATS_SUMMARY_DAYS)
    usd_per_rune = await d.pool_cache.get_usd_per_rune()
    return dataclasses.asdict(AlertRuneTransferStats.from_summary(summary, usd_per_rune=usd_per_rune))


async def block_scanner_info(ctx: DashboardContext) -> dict:
    state = await ScannerStateDB(ctx.deps.db, role='main').load_state()
    return {
        **state.model_dump(),
        'success_rate': state.success_rate,
        'lag_behind_thor': state.lag_behind_thor,
        'now': now_ts(),
    }
