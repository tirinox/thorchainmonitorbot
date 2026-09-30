import json
import logging
from types import SimpleNamespace

import pytest

from api.aionode.types import ThorPool, ThorModuleBalance, ThorLiquidityProvider
from jobs.fetch.pol_reserve import PolReserveFetcher, find_height_at_timestamp, utc_date_str
from lib.constants import ADR24_FIRST_DEPLOY_BLOCK, THOR_BLOCK_TIME
from lib.date_utils import DAY
from models.earnings_history import EarningsInterval, PoolEarnings
from models.pol_reserve import PolReservePoolSnapshot, PolReserveSnapshot, PolReserveDay, AlertPolReserveStats, \
    build_pol_reserve_day
from tests.fakes import FakeRedis

E8 = 10 ** 8
XRP = 'XRP.XRP'
TRX = 'TRON.TRX'
MODULE_ADDRESS = 'thor1fns25sytpf2gsdlg76g45620u5axm4mkrypqrh'


def _pool(asset=XRP, deposited=100, units=25, pool_units=100, balance_rune=1000, balance_asset=500):
    return PolReservePoolSnapshot(
        asset=asset,
        rune_deposited=deposited * E8,
        units=units * E8,
        pool_units=pool_units * E8,
        balance_rune=balance_rune * E8,
        balance_asset=balance_asset * E8,
        status='Available',
    )


# ---- Types ----

def test_thor_pool_parses_pol_reserve_fields():
    pool = ThorPool.from_json({
        'asset': XRP, 'balance_rune': '112473332381585', 'balance_asset': '56244278690146',
        'pool_units': '75081262698819', 'pol_reserve_rune_deposited': '56693427301951',
        'rolling_pool_liquidity_fee_rune': '4019970492',
    })
    assert pool.pol_reserve_rune_deposited == 56693427301951
    assert pool.rolling_pool_liquidity_fee_rune == 4019970492

    # nodes before ADR-024 do not have these fields
    assert ThorPool.from_json({'asset': XRP}).pol_reserve_rune_deposited == 0


def test_module_balance():
    empty = ThorModuleBalance.from_json({'name': 'pol_reserve', 'address': MODULE_ADDRESS, 'coins': []})
    assert empty.address == MODULE_ADDRESS
    assert empty.runes == 0

    funded = ThorModuleBalance.from_json({'name': 'pol_reserve', 'address': MODULE_ADDRESS,
                                          'coins': [{'denom': 'rune', 'amount': '980770'}]})
    assert funded.runes == 980770


# ---- Model ----

def test_pool_snapshot_math():
    p = _pool(deposited=600, units=25, pool_units=100, balance_rune=1000, balance_asset=500)
    assert p.share == pytest.approx(0.25)
    assert p.share_percent == pytest.approx(25.0)
    assert p.deeper_percent == pytest.approx(100 / 3)  # 0.25 / 0.75
    assert p.rune_held == pytest.approx(250.0)
    assert p.asset_held == pytest.approx(125.0)
    assert p.value_rune == pytest.approx(500.0)
    assert p.pnl_rune == pytest.approx(-100.0)
    assert p.pnl_percent == pytest.approx(-100 / 6)


def test_pool_snapshot_degenerate_shares():
    assert _pool(units=0, pool_units=0).share == 0.0
    assert _pool(units=100, pool_units=100).deeper_percent is None  # no pool without POL to compare with


def test_snapshot_totals_and_json_round_trip():
    snapshot = PolReserveSnapshot(
        height=123, timestamp=1000,
        pools=[_pool(XRP, deposited=600), _pool(TRX, deposited=50, units=10)],
        undeployed_rune=5 * E8, usd_per_rune=0.75,
    )
    assert snapshot.rune_deposited == pytest.approx(650.0)
    assert snapshot.value_rune == pytest.approx(500.0 + 200.0)
    assert snapshot.value_usd == pytest.approx(700.0 * 0.75)
    assert snapshot.active_pool_count == 2
    assert not snapshot.is_zero
    assert snapshot.find_pool(TRX).units == 10 * E8
    assert snapshot.find_pool('BTC.BTC') is None

    restored = PolReserveSnapshot.from_json(json.loads(json.dumps(snapshot.to_dict())))
    assert restored == snapshot

    assert PolReserveSnapshot(height=1, timestamp=1).is_zero


def test_build_day_attributes_fees_by_mean_share():
    start = PolReserveSnapshot(1, 0, pools=[_pool(XRP, deposited=100, units=10)])
    end = PolReserveSnapshot(2, DAY, pools=[
        _pool(XRP, deposited=400, units=30),
        _pool(TRX, deposited=50, units=20),  # a new pool, POL had no share in it at the start of the day
    ])

    day = build_pol_reserve_day(
        '2026-09-10', 0, start, end,
        cumulative_before=start.rune_deposited,
        usd_per_rune=0.5,
        system_income_rune=5000.0,
        pool_fees_rune={XRP: 1000.0, TRX: 100.0, 'BTC.BTC': 9999.0},
        pool_earnings_rune={XRP: 100.0},
    )

    assert day.deposited_by_pool == pytest.approx({XRP: 300.0, TRX: 50.0})
    assert day.deposited_rune == pytest.approx(350.0)
    assert day.cumulative_deposited_rune == pytest.approx(450.0)
    assert day.deposited_usd == pytest.approx(175.0)
    # XRP: (10% + 30%) / 2 of 1000; TRX: (0% + 20%) / 2 of 100
    assert day.fees_rune == pytest.approx(200.0 + 10.0)
    assert day.earnings_rune == pytest.approx(20.0)
    assert day.value_rune == pytest.approx(end.value_rune)
    assert day.avg_value_rune == pytest.approx((start.value_rune + end.value_rune) / 2)
    assert not day.partial


def test_build_day_without_start_snapshot():
    end = PolReserveSnapshot(2, DAY, pools=[_pool(XRP, deposited=70, units=10)])
    day = build_pol_reserve_day('2026-08-31', 0, None, end, pool_fees_rune={XRP: 100.0})
    assert day.deposited_rune == pytest.approx(70.0)
    assert day.cumulative_deposited_rune == pytest.approx(70.0)
    assert day.fees_rune == pytest.approx(5.0)
    assert day.avg_value_rune == pytest.approx(end.value_rune / 2)


def test_alert_stats_aggregates():
    days = [
        PolReserveDay('2026-09-01', 0, deposited_rune=100, usd_per_rune=0.5, avg_value_rune=1000,
                      fees_rune=10, earnings_rune=1),
        PolReserveDay('2026-09-02', DAY, deposited_rune=300, usd_per_rune=1.0, avg_value_rune=3000,
                      fees_rune=30, earnings_rune=3),
        PolReserveDay('2026-09-03', 2 * DAY, deposited_rune=50, usd_per_rune=2.0, avg_value_rune=4000,
                      fees_rune=5, earnings_rune=0.5, partial=True),
    ]
    current = PolReserveSnapshot(10, 3 * DAY, pools=[_pool(XRP, deposited=450, units=50)], usd_per_rune=2.0)
    stats = AlertPolReserveStats(current=current, days=days, system_income_bps=2000)

    assert stats.system_income_percent == pytest.approx(20.0)
    assert [d.date for d in stats.complete_days] == ['2026-09-01', '2026-09-02']
    assert stats.avg_daily_deposit_rune == pytest.approx(200.0)  # the partial day is left out
    assert stats.deposited_usd_at_cost == pytest.approx(50 + 300 + 100)
    assert stats.fees_rune() == pytest.approx(45.0)
    assert stats.fees_rune(net=True) == pytest.approx(4.5)
    assert stats.fees_rune(1) == pytest.approx(30.0)
    assert stats.fees_usd() == pytest.approx(5 + 30 + 10)

    # the last complete day: 30 / 3000 a day
    assert stats.apr_percent(1) == pytest.approx(365.0)
    # both complete days: 40 / 4000 value-days
    assert stats.apr_percent(7) == pytest.approx(365.0)
    assert stats.apr_percent(7, net=True) == pytest.approx(36.5)
    assert AlertPolReserveStats(current=current).apr_percent(7) is None

    assert stats.value_change_percent is None
    stats.previous = PolReserveSnapshot(5, DAY, pools=[_pool(XRP, units=40)])
    assert stats.value_change_percent == pytest.approx(25.0)


# ---- Block search ----

class _FakeChain:
    """Blocks are produced every block_time seconds, the block `height` has the timestamp `ts`"""

    def __init__(self, height, ts, block_time=6.26):
        self.height, self.ts, self.block_time = height, ts, block_time
        self.requests = 0

    def ts_of(self, height):
        return self.ts - (self.height - height) * self.block_time

    async def get_block_ts(self, height):
        self.requests += 1
        return self.ts_of(height)


@pytest.mark.asyncio
@pytest.mark.parametrize('block_time', [5.5, 6.0, 6.26, 7.3])
@pytest.mark.parametrize('seconds_ago', [10, DAY, 30 * DAY])
async def test_find_height_at_timestamp(block_time, seconds_ago):
    chain = _FakeChain(28_000_000, 1_790_000_000, block_time)
    target = chain.ts - seconds_ago

    height = await find_height_at_timestamp(target, chain.height, chain.ts, chain.get_block_ts,
                                            max_height=chain.height)

    assert 0 <= target - chain.ts_of(height) < THOR_BLOCK_TIME * 2
    assert chain.requests <= 4


@pytest.mark.asyncio
async def test_find_height_at_timestamp_is_clamped_to_the_chain():
    chain = _FakeChain(1000, 1_790_000_000)
    assert await find_height_at_timestamp(chain.ts + 500, chain.height, chain.ts, chain.get_block_ts,
                                          max_height=chain.height) == chain.height
    assert await find_height_at_timestamp(chain.ts_of(1) - 500, chain.height, chain.ts, chain.get_block_ts,
                                          max_height=chain.height) == 1


# ---- Fetcher ----

NOW_TS = 1_790_726_400 + 8 * 3600  # 30 September 2026, 08:00 UTC
NOW_HEIGHT = 28_040_000
BLOCK_TIME = 6.25
DEPLOY_PER_BLOCK = 2  # RUNE


class _FakeConnector:
    """XRP pool only. The module deploys DEPLOY_PER_BLOCK RUNE every block since ADR24_FIRST_DEPLOY_BLOCK."""

    def __init__(self):
        self.pool_requests = []
        self.fail_members = False

    @staticmethod
    def _blocks_deployed(height):
        return max(0, (height or NOW_HEIGHT) - ADR24_FIRST_DEPLOY_BLOCK)

    async def query_module_balance(self, module_name, height=None):
        return ThorModuleBalance(module_name, MODULE_ADDRESS, {'rune': 7 * E8})

    async def query_pools(self, height=None):
        self.pool_requests.append(height)
        return [
            ThorPool(asset=XRP, balance_rune=1_000_000 * E8, balance_asset=500_000 * E8,
                     pool_units=4_000_000 * E8, status='Available',
                     pol_reserve_rune_deposited=self._blocks_deployed(height) * DEPLOY_PER_BLOCK * E8),
            ThorPool(asset='BTC.BTC', balance_rune=10 * E8, balance_asset=E8, pool_units=E8),
        ]

    async def query_liquidity_provider(self, asset, address, height=None):
        assert asset == XRP and address == MODULE_ADDRESS
        if self.fail_members:
            return None
        return ThorLiquidityProvider(
            asset=asset, asset_address='', rune_address=address, last_add_height=0, last_withdraw_height=0,
            units=self._blocks_deployed(height) * E8, pending_rune=0, pending_asset=0, pending_tx_id='',
            rune_deposit_value=0, asset_deposit_value=0,
        )

    async def query_tendermint_block_raw(self, height):
        ts = NOW_TS - (NOW_HEIGHT - height) * BLOCK_TIME
        time_str = f'{utc_date_str(ts)}T{int(ts % DAY // 3600):02}:{int(ts % 3600 // 60):02}:{ts % 60:012.9f}Z'
        return {'result': {'block': {'header': {'time': time_str}}}}


class _FakeMidgard:
    async def query_earnings(self, from_ts=0, to_ts=0, count=0, interval=''):
        today_start = NOW_TS // DAY * DAY
        return SimpleNamespace(intervals=[
            EarningsInterval(
                avg_node_count=100, block_rewards=0, bonding_earnings=0, earnings=5000 * E8,
                end_time=today_start - (i - 1) * DAY, liquidity_earnings=0, liquidity_fees=0,
                pools=[PoolEarnings(0, 100 * E8, XRP, 0, 0, 0, 1000 * E8)],
                rune_price_usd=0.5, start_time=today_start - i * DAY,
            ) for i in range(count - 1, -1, -1)
        ])


class _FakeMimir:
    async def get_mimir_holder(self):
        return self

    def get_constant(self, name, default=0, const_type=int):
        return {'POLRESERVESYSTEMINCOMEBPS': 2000, 'POLRESERVEMAXDEPLOYMENT': 100 * E8}.get(name, default)


class _FakeDB:
    def __init__(self):
        self.redis = FakeRedis()

    async def get_redis(self):
        return self.redis


class _FakeValue:
    def __init__(self, value):
        self.value = value

    async def get_thor_block(self):
        return self.value

    async def get_usd_per_rune(self):
        return self.value


def _make_fetcher(days, monkeypatch) -> PolReserveFetcher:
    monkeypatch.setattr('jobs.fetch.pol_reserve.now_ts', lambda: NOW_TS)
    fetcher = PolReserveFetcher.__new__(PolReserveFetcher)
    connector = _FakeConnector()
    fetcher.deps = SimpleNamespace(
        thor_connector=connector,
        thor_connector_archive=connector,
        midgard_connector=_FakeMidgard(),
        mimir_cache=_FakeMimir(),
        db=_FakeDB(),
        last_block_cache=_FakeValue(NOW_HEIGHT),
        pool_cache=_FakeValue(0.75),
    )
    fetcher.days = days
    fetcher.logger = logging.getLogger('test')
    fetcher._module_address = ''
    return fetcher


@pytest.mark.asyncio
async def test_fetcher_builds_history_and_caches_day_ends(monkeypatch):
    fetcher = _make_fetcher(3, monkeypatch)
    connector: _FakeConnector = fetcher.deps.thor_connector

    data = await fetcher.fetch()

    assert data.system_income_bps == 2000
    assert data.max_deployment_rune == pytest.approx(100.0)
    assert data.module_address == MODULE_ADDRESS

    current = data.current
    assert current.height == NOW_HEIGHT
    assert current.usd_per_rune == 0.75
    assert current.undeployed_rune == 7 * E8
    assert [p.asset for p in current.pools] == [XRP]  # BTC has no POL reserve deposits
    assert current.rune_deposited == pytest.approx((NOW_HEIGHT - ADR24_FIRST_DEPLOY_BLOCK) * DEPLOY_PER_BLOCK)

    assert [d.date for d in data.days] == ['2026-09-27', '2026-09-28', '2026-09-29', '2026-09-30']
    assert [d.partial for d in data.days] == [False, False, False, True]

    blocks_per_day = DAY / BLOCK_TIME
    for day in data.complete_days:
        # the day boundaries are found within a couple of blocks
        assert day.deposited_rune == pytest.approx(blocks_per_day * DEPLOY_PER_BLOCK, abs=4 * DEPLOY_PER_BLOCK)
        assert day.usd_per_rune == 0.5
        assert day.system_income_rune == pytest.approx(5000.0)
        assert day.fees_rune > 0
        assert day.earnings_rune == pytest.approx(day.fees_rune / 10)
    assert data.days[-1].usd_per_rune == 0.75
    assert data.days[-1].fees_rune == 0
    assert data.days[-1].cumulative_deposited_rune == pytest.approx(current.rune_deposited)
    assert data.days[-1].deposited_rune == pytest.approx(8 * 3600 / BLOCK_TIME * DEPLOY_PER_BLOCK,
                                                         abs=4 * DEPLOY_PER_BLOCK)

    # 3 days and the day before them as the starting point
    cached = fetcher.deps.db.redis.hashes[PolReserveFetcher.DB_KEY_DAY_END]
    assert sorted(cached) == ['2026-09-26', '2026-09-27', '2026-09-28', '2026-09-29']
    historical_requests = [h for h in connector.pool_requests if h]
    assert len(historical_requests) == 4

    # the second run takes the finished days from the DB
    connector.pool_requests.clear()
    again = await fetcher.fetch()
    assert connector.pool_requests == [None]
    assert [d.deposited_rune for d in again.days] == pytest.approx([d.deposited_rune for d in data.days])


@pytest.mark.asyncio
async def test_fetcher_stops_at_the_activation(monkeypatch):
    fetcher = _make_fetcher(60, monkeypatch)

    data = await fetcher.fetch()

    # NOW_HEIGHT is about 29 days of blocks after the first deployment
    assert data.days[0].date == utc_date_str(NOW_TS - (NOW_HEIGHT - ADR24_FIRST_DEPLOY_BLOCK) * BLOCK_TIME)
    assert len(data.days) < 32
    assert data.days[0].deposited_rune == pytest.approx(data.days[0].cumulative_deposited_rune)
    assert sum(d.deposited_rune for d in data.days) == pytest.approx(data.current.rune_deposited)


@pytest.mark.asyncio
async def test_fetcher_does_not_cache_incomplete_snapshots(monkeypatch):
    fetcher = _make_fetcher(2, monkeypatch)
    fetcher.deps.thor_connector.fail_members = True

    with pytest.raises(ConnectionError):
        await fetcher.fetch()

    assert not fetcher.deps.db.redis.hashes[PolReserveFetcher.DB_KEY_DAY_END]


# ---- Infographic ----

def test_alert_to_dict_is_plain_json_for_the_template():
    days = [
        PolReserveDay('2026-09-01', 0, deposited_rune=100, deposited_by_pool={XRP: 100}, usd_per_rune=0.5,
                      cumulative_deposited_rune=100, avg_value_rune=1000, fees_rune=10, earnings_rune=1),
        PolReserveDay('2026-09-02', DAY, deposited_rune=300, deposited_by_pool={XRP: 300}, usd_per_rune=1.0,
                      cumulative_deposited_rune=400, avg_value_rune=3000, fees_rune=30, earnings_rune=3),
        PolReserveDay('2026-09-03', 2 * DAY, deposited_rune=50, usd_per_rune=2.0, partial=True),
    ]
    current = PolReserveSnapshot(10, 3 * DAY, pools=[
        _pool('TRON.USDT-TR7NHQJEKQXGTCI8Q8ZY4PL8OTSZGJLJ6T', deposited=450, units=50),
    ], usd_per_rune=2.0)
    stats = AlertPolReserveStats(current=current, days=days, system_income_bps=2000, max_deployment_rune=100,
                                 chart_days=2)

    params = json.loads(json.dumps(stats.to_dict()))

    assert params['total_days'] == 3
    assert params['start_date'] == '2026-09-01'
    assert params['previous'] is None
    assert params['system_income_percent'] == 20.0

    assert [d['date'] for d in params['daily']] == ['2026-09-02', '2026-09-03']  # chart_days
    assert params['chart_days'] == 2

    pool = params['pools'][0]
    assert pool['ticker'] == 'USDT'
    assert pool['value_usd'] == pytest.approx(current.value_usd)

    cost = 100 * 0.5 + 300 * 1.0 + 50 * 2.0
    assert params['current']['deposited_usd_at_cost'] == pytest.approx(cost)
    assert params['current']['pnl_usd'] == pytest.approx(current.value_usd - cost)
    assert params['deposits'] == pytest.approx({
        'avg_daily_rune': 200.0, 'peak_rune': 300.0, 'last_day_rune': 300.0, 'last_7d_rune': 400.0,
    } | {'peak_date': '2026-09-02'})
    assert params['fees']['gross']['rune'] == pytest.approx(40.0)
    assert params['fees']['net']['rune'] == pytest.approx(4.0)
    assert params['fees']['net']['apr_30d'] == pytest.approx(36.5)

    stats.previous = PolReserveSnapshot(5, DAY, pools=[_pool(XRP, units=40)], usd_per_rune=1.0)
    assert stats.to_dict()['previous']['value_usd'] == pytest.approx(stats.previous.value_usd)


# ---- Scheduled job and texts ----

def _sample_stats() -> AlertPolReserveStats:
    days = [
        PolReserveDay('2026-09-01', 0, deposited_rune=100, usd_per_rune=0.5, avg_value_rune=1000,
                      fees_rune=10, earnings_rune=1),
        PolReserveDay('2026-09-02', DAY, deposited_rune=300, usd_per_rune=1.0, partial=True),
    ]
    current = PolReserveSnapshot(10, 2 * DAY, pools=[_pool(XRP, deposited=400, units=50)], usd_per_rune=2.0)
    return AlertPolReserveStats(current=current, days=days, system_income_bps=2000, max_deployment_rune=100)


class _FakeReserveFetcher:
    def __init__(self, data):
        self.data = data

    async def fetch_and_remember(self):
        return self.data


def _make_executor(data, handled: list):
    from contextlib import nullcontext
    from notify.pub_configure import PublicAlertJobExecutor

    async def handle_data(d):
        handled.append(d)

    executor = PublicAlertJobExecutor.__new__(PublicAlertJobExecutor)
    executor.logger = logging.getLogger('test')
    executor.pol_reserve_fetcher = _FakeReserveFetcher(data)
    executor.deps = SimpleNamespace(
        db=_FakeDB(),
        alert_presenter=SimpleNamespace(handle_data=handle_data),
        broadcaster=SimpleNamespace(override_channels=lambda channels: nullcontext(), test_channels=['test']),
    )
    return executor


@pytest.mark.asyncio
async def test_job_compares_with_the_previous_real_post():
    from lib.run_context import run_context, RunMode

    handled = []
    executor = _make_executor(_sample_stats(), handled)
    state_key = 'PolReserveSnapshot:PrevState'

    await executor.job_pol_summary_adr024()
    assert handled[-1].previous is None
    saved = executor.deps.db.redis.strings[state_key]
    assert PolReserveSnapshot.from_json(json.loads(saved)) == handled[-1].current

    # the next run is compared with the saved state
    newer = _sample_stats()
    newer.current.height = 20
    newer.current.pools[0].units = 60 * E8
    executor.pol_reserve_fetcher = _FakeReserveFetcher(newer)

    # a test send must not move the saved state
    with run_context(RunMode.TEST):
        await executor.job_pol_summary_adr024()
    assert handled[-1].previous.height == 10
    assert handled[-1].value_change_percent == pytest.approx(20.0)
    assert executor.deps.db.redis.strings[state_key] == saved

    await executor.job_pol_summary_adr024()
    assert json.loads(executor.deps.db.redis.strings[state_key])['height'] == 20


@pytest.mark.asyncio
async def test_job_refuses_to_post_empty_pol():
    handled = []
    data = AlertPolReserveStats(current=PolReserveSnapshot(1, 1))
    with pytest.raises(ValueError):
        await _make_executor(data, handled).job_pol_summary_adr024()
    assert not handled


def test_job_is_registered():
    from notify.pub_configure import PublicAlertJobExecutor, PubAlertJobNames
    assert PubAlertJobNames.POL_SUMMARY_ADR024 == 'pol_summary_adr024'
    assert PubAlertJobNames.POL_SUMMARY_ADR024 in PublicAlertJobExecutor.AVAILABLE_TYPES


@pytest.mark.parametrize('loc_path', [
    'comm.localization.eng_base.BaseLocalization',
    'comm.localization.rus.RussianLocalization',
    'comm.localization.twitter_eng.TwitterEnglishLocalization',
])
def test_texts(loc_path):
    import importlib
    module, cls_name = loc_path.rsplit('.', 1)
    loc = getattr(importlib.import_module(module), cls_name).__new__(getattr(importlib.import_module(module), cls_name))

    stats = _sample_stats()
    text = loc.notification_text_pol_reserve_stats(stats)
    assert 'ADR-024' in text
    assert 'XRP' in text
    assert '50' in text  # share of the pool
    assert len(text) < 1000  # fits a Telegram photo caption

    stats.previous = PolReserveSnapshot(5, DAY, pools=[_pool(XRP, units=40)], usd_per_rune=2.0)
    assert '25' in loc.notification_text_pol_reserve_stats(stats)  # the value has grown by 25%
