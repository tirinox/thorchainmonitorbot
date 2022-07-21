import asyncio

import pytest

from services.lib.cooldown import CooldownBiTrigger
from services.lib.date_utils import now_ts
from services.lib.db import DB


@pytest.fixture(scope="function")
def db():
    loop = asyncio.get_event_loop()
    return DB(loop)


@pytest.mark.asyncio
async def test_cd_trigger(db):
    await db.get_redis()

    trigger = CooldownBiTrigger(db, 'test_evt', 1.0, 1.0)
    assert await trigger.turn_on()
    assert not await trigger.turn_on()
    assert await trigger.turn_off()
    assert not await trigger.turn_off()
    print('Wait a sec!')
    await asyncio.sleep(1.1)
    assert await trigger.turn_off()
    print('Wait a sec!')
    await asyncio.sleep(1.1)
    assert await trigger.turn_on()
    print('OK')


@pytest.mark.asyncio
async def test_cd_diff_cd(db):
    await db.get_redis()

    trigger = CooldownBiTrigger(db, 'test_evt_2', 1.0, 2.0)
    await trigger.turn_on()
    assert await trigger.turn_off()
    await asyncio.sleep(1.1)
    assert not await trigger.turn_off()
    await asyncio.sleep(1.1)
    assert await trigger.turn_off()


@pytest.mark.asyncio
async def test_cd_trigger_spam(db):
    await db.get_redis()

    trigger = CooldownBiTrigger(db, 'test_evt_3', 0.1, 0.1, switch_cooldown_sec=0.02)
    assert await trigger.turn_on()
    assert not await trigger.turn_on()
    assert not await trigger.turn_off()

    # normal operation
    await asyncio.sleep(0.11)
    assert await trigger.turn_off()
    await asyncio.sleep(0.11)
    assert await trigger.turn_on()

    # fast switch
    await asyncio.sleep(0.01)
    assert not await trigger.turn_off()  # early
    assert not await trigger.turn_off()  # early
    await asyncio.sleep(0.015)
    assert await trigger.turn_off()

    await asyncio.sleep(0.06)

    # now off
    assert await trigger.turn_on()  # early
    assert not await trigger.turn_on()  # early
    await asyncio.sleep(0.15)
    assert await trigger.turn_on()


@pytest.mark.asyncio
async def test_cd_last_switch(db):
    await db.get_redis()

    t0 = now_ts()
    trigger = CooldownBiTrigger(db, 'test_evt_4', 0.2, 0.2, track_last_switch_ts=True)
    await trigger.turn_on()
    t1 = await trigger.get_last_switch_ts()
    assert t1 - t0 < 0.1
    await trigger.turn_off()

    t0 = now_ts()
    await asyncio.sleep(0.21)
    await trigger.turn_on()
    await asyncio.sleep(0.21)
    await trigger.turn_on()
    await asyncio.sleep(0.21)
    await trigger.turn_on()
    t1 = await trigger.get_last_switch_ts()
    assert t1 > 0.0 and t1 - t0 < 0.22
    t11 = await trigger.get_last_update_ts(state=True)
    assert t11 > 0.0 and t11 - t0 > 0.6

    await trigger.turn_off()
    t12 = await trigger.get_last_switch_ts()
    assert t12 > 0.0 and now_ts() - t12 < 0.1
