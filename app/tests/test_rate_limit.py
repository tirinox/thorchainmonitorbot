import asyncio

import pytest

from lib.db import DB
from lib.depcont import DepContainer
from lib.rate_limit import RateLimiter, RateLimitCooldown


@pytest.fixture(scope="function")
def deps():
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.db = DB()
    return d


LIMIT_N = 10
LIMIT_T = 1.0
CD_T = 0.5


@pytest.yield_fixture()
async def rate_limiter(deps):
    rr = RateLimiter(deps.db, 'TestRL', LIMIT_N, LIMIT_T)
    await deps.db.get_redis()
    yield rr
    await rr.clear()


@pytest.yield_fixture()
async def rate_limiter_cd(deps):
    rr = RateLimitCooldown(deps.db, 'TestRCD', LIMIT_N, LIMIT_T, CD_T)
    await deps.db.get_redis()
    yield rr
    await rr.clear()


@pytest.mark.asyncio
async def test_rate_limit_burst(rate_limiter: RateLimiter):
    lim = rate_limiter.is_limited
    for _ in range(LIMIT_N):
        assert not await lim()
    assert await lim()


@pytest.mark.asyncio
async def test_rate_limit_burst_normal(rate_limiter: RateLimiter):
    lim = rate_limiter.is_limited
    for _ in range(LIMIT_N - 1):
        assert not await lim()
    await asyncio.sleep(LIMIT_T)
    for _ in range(LIMIT_N - 1):
        assert not await lim()
    await asyncio.sleep(LIMIT_T)

    for _ in range(LIMIT_N):
        assert not await lim()
    assert await lim()


@pytest.mark.asyncio
async def test_rate_limit_normal_flow(rate_limiter: RateLimiter):
    lim = rate_limiter.is_limited
    pause = LIMIT_T / (LIMIT_N - 1)
    # print(f'{pause = } sec, {LIMIT_N = }, {LIMIT_T = } sec')
    for _ in range(LIMIT_N * 2):
        assert not await lim()
        await asyncio.sleep(pause)


@pytest.mark.asyncio
async def test_rate_limit_cooldown(rate_limiter_cd: RateLimitCooldown):
    r = rate_limiter_cd

    for i in range(LIMIT_N):
        assert await r.hit() == r.GOOD

    assert await r.hit() == r.HIT_LIMIT

    assert await r.hit() == r.ON_COOLDOWN
    assert await r.hit() == r.ON_COOLDOWN

    await asyncio.sleep(CD_T + LIMIT_T)
    assert await r.hit() == r.GOOD
    assert await r.hit() == r.GOOD
