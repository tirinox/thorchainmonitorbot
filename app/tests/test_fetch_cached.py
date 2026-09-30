import asyncio

import pytest

import jobs.fetch.base as base_module
from jobs.fetch.base import BaseFetcher
from lib.depcont import DepContainer

T0 = 1_700_000_000.0


class CountingFetcher(BaseFetcher):
    def __init__(self, delay=0.0):
        super().__init__(DepContainer(), sleep_period=0)
        self.calls = 0
        self.delay = delay

    async def fetch(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return f'data-{self.calls}'


@pytest.fixture
def clock(monkeypatch):
    now = {'t': T0}
    monkeypatch.setattr(base_module, 'now_ts', lambda: now['t'])
    return now


@pytest.mark.asyncio
async def test_fetch_cached_reuses_fresh_data(clock):
    f = CountingFetcher()
    assert await f.fetch_cached(60) == 'data-1'
    clock['t'] += 59
    assert await f.fetch_cached(60) == 'data-1'
    assert f.calls == 1


@pytest.mark.asyncio
async def test_fetch_cached_refetches_stale_data(clock):
    f = CountingFetcher()
    assert await f.fetch_cached(60) == 'data-1'
    clock['t'] += 60
    assert await f.fetch_cached(60) == 'data-2'
    assert f.calls == 2


@pytest.mark.asyncio
async def test_fetch_cached_reuses_data_of_scheduled_run(clock):
    f = CountingFetcher()
    assert await f.fetch_and_remember() == 'data-1'
    assert await f.fetch_cached(60) == 'data-1'
    assert f.calls == 1


@pytest.mark.asyncio
async def test_fetch_cached_concurrent_callers_share_one_fetch(clock):
    f = CountingFetcher(delay=0.01)
    results = await asyncio.gather(*(f.fetch_cached(60) for _ in range(5)))
    assert results == ['data-1'] * 5
    assert f.calls == 1


@pytest.mark.asyncio
async def test_fetch_cached_does_not_remember_errors(clock):
    class FailingOnce(CountingFetcher):
        async def fetch(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError('boom')
            return 'ok'

    f = FailingOnce()
    with pytest.raises(RuntimeError):
        await f.fetch_cached(60)
    assert await f.fetch_cached(60) == 'ok'
