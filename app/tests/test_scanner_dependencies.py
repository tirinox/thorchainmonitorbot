import logging
from types import SimpleNamespace

import pytest

from lib.config import Config
from models.sched import IntervalCfg, SchedJobCfg
from notify.pub_configure import PublicAlertJobExecutor, PubAlertJobNames as Jobs
from notify.pub_scheduler import PublicScheduler
from tests.fakes import FakePubSubRedis

SCANNER_JOBS = {Jobs.RAPID_SWAP_STATS, Jobs.RUNE_TRANSFER_STATS, Jobs.LIMIT_SWAP_STATS, Jobs.APP_LAYER_STATS,
                Jobs.KEY_METRICS, Jobs.TRADE_ASSET_SUMMARY}


def _executor(config: dict):
    # skip __init__: it builds every fetcher
    executor = PublicAlertJobExecutor.__new__(PublicAlertJobExecutor)
    executor.deps = SimpleNamespace(cfg=Config(data=config), db=SimpleNamespace(redis=FakePubSubRedis()), loop=None,
                                   emergency=None)
    return executor


@pytest.mark.parametrize('config, expected', [
    ({}, {}),
    ({'native_scanner': {'enabled': False}}, {job: 'needs native_scanner.enabled' for job in SCANNER_JOBS}),
    ({'tx': {'enabled': False}}, {Jobs.KEY_METRICS: 'needs tx.enabled', Jobs.TRADE_ASSET_SUMMARY: 'needs tx.enabled'}),
    ({'native_scanner': {'wasm': {'enabled': False}}}, {Jobs.APP_LAYER_STATS: 'needs native_scanner.wasm.enabled'}),
    ({'native_scanner': {'limit_swaps': {'enabled': False}}},
     {Jobs.LIMIT_SWAP_STATS: 'needs native_scanner.limit_swaps.enabled'}),
])
def test_job_types_without_data(config, expected):
    assert _executor(config).job_types_without_data() == expected


def test_both_sources_off():
    reasons = _executor({'native_scanner': {'enabled': False}, 'tx': {'enabled': False}}).job_types_without_data()
    assert reasons[Jobs.KEY_METRICS] == 'needs native_scanner.enabled, tx.enabled'


@pytest.mark.asyncio
async def test_jobs_without_data_are_known_but_not_scheduled(caplog):
    executor = _executor({'native_scanner': {'enabled': False}})
    scheduler: PublicScheduler = await executor.configure_jobs()

    assert set(scheduler._registered_jobs) == set(PublicAlertJobExecutor.AVAILABLE_TYPES) - SCANNER_JOBS
    assert set(scheduler._disabled_job_types) == SCANNER_JOBS

    scheduler._scheduled_jobs = [
        SchedJobCfg(id='weekly', func=Jobs.KEY_METRICS, enabled=True, variant='interval',
                    interval=IntervalCfg(days=7)),
    ]
    with caplog.at_level(logging.WARNING):
        await scheduler.apply_scheduler_configuration()
    assert scheduler.scheduler.get_jobs() == []
    assert "Job type key_metrics is turned off: needs native_scanner.enabled; job 'weekly' is not scheduled." \
           in caplog.text
    assert 'ERROR' not in [r.levelname for r in caplog.records]

    with pytest.raises(RuntimeError, match='key_metrics is turned off: needs native_scanner.enabled'):
        await scheduler.run_job_now_by_id('weekly')
    with pytest.raises(RuntimeError, match='rapid_swap_stats is turned off'):
        await scheduler.run_job_by_function(Jobs.RAPID_SWAP_STATS)


@pytest.mark.asyncio
async def test_price_alert_without_volume_recorder():
    from notify.public.price_notify import PriceChangeNotifier

    class FakePriceRecorder:
        async def get_prices(self, _period):
            return [], [], []

        async def get_tcy_prices(self, _period):
            return []

    async def get_ph():
        return SimpleNamespace(usd_per_rune=1.0, btc_per_rune=0.00001)

    notifier = PriceChangeNotifier.__new__(PriceChangeNotifier)
    notifier.deps = SimpleNamespace(volume_recorder=None, pool_cache=SimpleNamespace(get=get_ph),
                                    chain_info=SimpleNamespace(state_list=[]))
    notifier.ath_sticker_iter = iter([])
    notifier.price_recorder = FakePriceRecorder()
    notifier.price_graph_period = 7 * 24 * 3600

    async def no_history():
        return {}

    notifier.get_historical_price_dict = no_history
    event = await notifier.make_event(SimpleNamespace(), ath=False)
    assert event.volumes == []
