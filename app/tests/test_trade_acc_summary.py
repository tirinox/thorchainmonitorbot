import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.aionode.types import ThorTradeUnits, ThorTradeAccount
from lib.date_utils import DAY
from models.swap_history import SwapHistoryResponse, SwapsHistoryEntry
from models.trade_acc import TradeAccountVaults, TradeAccountStats, AlertTradeAccountStats
from models.vol_n import TxMetricType as T

E8 = 10 ** 8
BTC = 'BTC.BTC'
ETH = 'ETH.ETH'
USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
PRICES = {BTC: 100_000.0, ETH: 4_000.0, USDC: 1.0}
T0 = 1_790_000_000 // DAY * DAY  # midnight UTC


def _vaults(depths: dict, holders: dict) -> TradeAccountVaults:
    """depths: pool name => amount of the trade asset; holders: pool name => list of owner addresses"""
    pools = {name: SimpleNamespace(asset=name, usd_per_asset=price) for name, price in PRICES.items()}
    units = [ThorTradeUnits(name.replace('.', '~', 1), int(amount * E8), int(amount * E8))
             for name, amount in depths.items()]
    traders = {
        name.replace('.', '~', 1): [ThorTradeAccount(name.replace('.', '~', 1), E8, owner, 0, 0) for owner in owners]
        for name, owners in holders.items()
    }
    return TradeAccountVaults.from_trade_units(units, pools, traders, [])


def _day(i, trade_usd, total_usd):
    half = trade_usd / 2 * 100  # Midgard gives USD volumes in cents
    return SwapsHistoryEntry.from_json({
        'startTime': T0 + i * DAY, 'endTime': T0 + (i + 1) * DAY,
        'toTradeVolumeUSD': half, 'fromTradeVolumeUSD': half, 'totalVolumeUSD': total_usd * 100,
        'toTradeCount': 10, 'fromTradeCount': 5, 'totalCount': 20 if total_usd else 0,
    })


def _alert(with_previous=True, chart_days=3) -> AlertTradeAccountStats:
    curr = _vaults({BTC: 2.0, ETH: 10.0, USDC: 30_000.0},
                   {BTC: ['a', 'b'], ETH: ['a', 'c', 'd'], USDC: ['e']})
    prev = _vaults({BTC: 1.0, ETH: 10.0}, {BTC: ['a'], ETH: ['a', 'c']}) if with_previous else None

    # 4 whole days and the running one, which Midgard reports empty
    days = [_day(0, 100, 400), _day(1, 200, 400), _day(2, 300, 600), _day(3, 400, 800), _day(4, 0, 0)]
    history = SwapHistoryResponse(intervals=days, meta=SwapsHistoryEntry.zero())

    return AlertTradeAccountStats(
        curr=TradeAccountStats(
            {T.SWAP: 50, T.TRADE_SWAP: 40, T.TRADE_DEPOSIT: 3, T.TRADE_WITHDRAWAL: 2},
            {T.usd_key(T.TRADE_DEPOSIT): 5000.0, T.usd_key(T.TRADE_WITHDRAWAL): 2000.0},
            curr,
        ),
        prev=TradeAccountStats({T.TRADE_SWAP: 30}, {}, prev),
        swap_stats=SwapHistoryResponse(intervals=days[-3:], meta=history.meta),
        period_sec=DAY,
        daily_history=history,
        chart_days=chart_days,
    )


def test_to_dict_is_plain_json_for_the_template():
    params = json.loads(json.dumps(_alert().to_dict()))

    assert params['period_days'] == 1
    cur = params['current']
    assert cur['value_usd'] == pytest.approx(2 * 100_000 + 10 * 4_000 + 30_000)
    assert cur['holders'] == 6
    assert cur['unique_holders'] == 5  # "a" holds two assets
    assert cur['asset_count'] == 3
    assert cur['swap_count'] == 40 and cur['all_swap_count'] == 50
    assert cur['deposit_usd'] == 5000.0 and cur['withdrawal_count'] == 2
    # the same numbers as the text: the last whole day and the one before
    assert cur['trade_volume_usd'] == pytest.approx(400)
    assert params['previous']['trade_volume_usd'] == pytest.approx(300)
    assert params['previous']['value_usd'] == pytest.approx(140_000)
    assert params['previous']['holders'] == 3

    assets = params['assets']
    assert [a['pool'] for a in assets] == [BTC, ETH, USDC]  # by value
    assert [a['name'] for a in assets] == ['BTC', 'ETH', 'ETH.USDC']
    assert assets[0]['asset'] == 'BTC~BTC'
    assert assets[0]['amount'] == pytest.approx(2.0)
    assert assets[0]['holders'] == 2 and assets[0]['prev_holders'] == 1
    assert assets[0]['prev_value_usd'] == pytest.approx(100_000)
    assert sum(a['share'] for a in assets) == pytest.approx(100)
    assert assets[2]['prev_value_usd'] is None  # a new asset

    # the running day is left out, the chart keeps the last chart_days whole days
    assert [d['trade_volume_usd'] for d in params['daily']] == pytest.approx([200, 300, 400])
    assert params['daily'][-1]['date'] == datetime.fromtimestamp(T0 + 3 * DAY, tz=timezone.utc).date().isoformat()
    assert params['daily'][-1]['all_swap_volume_usd'] == pytest.approx(800)
    assert params['daily'][-1]['trade_swap_count'] == 15


def test_to_dict_without_previous_vaults():
    params = _alert(with_previous=False).to_dict()
    assert params['previous']['value_usd'] is None
    assert params['previous']['holders'] is None
    assert params['previous']['swap_count'] == 30  # the counters still have the previous period
    assert all(a['prev_value_usd'] is None and a['prev_holders'] is None for a in params['assets'])


def test_to_dict_without_history():
    params = _alert()._replace(daily_history=None).to_dict()
    assert params['daily'] == []


@pytest.fixture(scope='module')
def renderer():
    pytest.importorskip('playwright')
    from renderer.engine import RendererEngine
    return RendererEngine(templates_dir=os.path.join(os.path.dirname(__file__), '..', 'renderer', 'templates'))


@pytest.mark.parametrize('params', [
    _alert().to_dict(),
    _alert(with_previous=False).to_dict(),
    {**_alert().to_dict(), 'assets': [], 'daily': [], 'previous': None},
], ids=['full', 'no-previous', 'empty'])
def test_template_renders(renderer, params):
    result = renderer.render_template_to_html('trade_asset_summary.jinja2', params)
    assert (result.viewport_width, result.viewport_height) == (1440, 1180)
    html = result.html_content
    assert 'TRADE ASSETS' in html
    assert 'Last 24H' in html
    if params['assets']:
        assert 'ETH.USDC' in html
    else:
        assert 'No data' in html


def test_template_renders_the_demo(renderer):
    from renderer.demo import load_demo
    demo = load_demo('trade_asset_summary')
    assert demo['template_name'] == 'trade_asset_summary.jinja2'
    html = renderer.render_template_to_html(demo['template_name'], demo['parameters']).html_content
    assert 'others' in html  # more assets than the list shows


@pytest.mark.parametrize('loc_path', [
    'comm.localization.eng_base.BaseLocalization',
    'comm.localization.rus.RussianLocalization',
])
def test_caption_fits_a_photo(loc_path):
    import importlib
    module, cls_name = loc_path.rsplit('.', 1)
    cls = getattr(importlib.import_module(module), cls_name)
    loc = cls.__new__(cls)
    text = loc.notification_text_trade_account_summary(_alert())
    assert 'BTC' in text
    assert '$270.0K' in text  # the total value of the trade assets is in dollars
    assert len(text) < 1024  # Telegram photo caption limit
