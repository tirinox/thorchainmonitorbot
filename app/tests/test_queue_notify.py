from types import SimpleNamespace

import pytest

import lib.cooldown
from lib.config import Config
from lib.date_utils import HOUR
from lib.flagship import Flagship
from notify.public.queue_notify import QueueNotifier
from tests.fakes import FakeDB


class FakeSeries:
    def __init__(self):
        self.value = 0.0

    async def average(self, period, key):
        return self.value


class Collector:
    def __init__(self):
        self.alerts = []

    async def on_data(self, sender, data):
        self.alerts.append('free' if data.is_free else 'congested')

    def take(self):
        alerts, self.alerts = self.alerts, []
        return alerts


@pytest.mark.asyncio
async def test_queue_free_is_told_once_after_a_congestion(monkeypatch):
    cfg = Config(data={'queue': {
        'cooldown': 3600,
        'threshold': {'avg_period': '10m', 'congested': 20, 'free': 2},
    }})
    db = FakeDB()
    notifier = QueueNotifier(SimpleNamespace(cfg=cfg, db=db, flagship=Flagship(db)))
    collector = Collector()
    notifier.add_subscriber(collector)
    series = FakeSeries()

    clock = [1_000_000.0]
    monkeypatch.setattr(lib.cooldown, 'now_ts', lambda: clock[0])

    async def tick(value, hours_later=0.0):
        clock[0] += hours_later * HOUR
        series.value = value
        await notifier.handle_entry('swap', series)
        return collector.take()

    # the queue has never been congested: there is nothing to announce, however long it stays empty
    assert await tick(0) == []
    assert await tick(0, hours_later=2) == []
    assert await tick(1, hours_later=24) == []

    assert await tick(50) == ['congested']
    assert await tick(60, hours_later=0.5) == []
    assert await tick(60, hours_later=1) == ['congested']  # still congested: a reminder once per cooldown
    assert await tick(10, hours_later=0.1) == []  # between the thresholds

    assert await tick(0, hours_later=0.1) == ['free']
    assert await tick(0, hours_later=2) == []
    assert await tick(0, hours_later=48) == []

    assert await tick(50) == ['congested']
    assert await tick(1, hours_later=0.1) == ['free']
