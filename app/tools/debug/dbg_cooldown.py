import asyncio
import logging

from services.lib.config import Config
from services.lib.cooldown import CooldownBiTrigger
from services.lib.db import DB
from services.lib.depcont import DepContainer

deps = DepContainer()
deps.cfg = Config()

logging.basicConfig(level=logging.DEBUG)

deps.loop = asyncio.get_event_loop()
deps.db = DB(deps.loop)


async def test_cd_trigger():
    trigger = CooldownBiTrigger(deps.db, 'test_evt', 2.0)
    assert await trigger.turn_on()
    assert not await trigger.turn_on()
    assert await trigger.turn_off()
    assert not await trigger.turn_off()
    print('Wait a sec!')
    await asyncio.sleep(2.1)
    assert await trigger.turn_off()
    print('Wait a sec!')
    await asyncio.sleep(2.1)
    assert await trigger.turn_on()
    print('OK')


if __name__ == '__main__':
    deps.loop.run_until_complete(test_cd_trigger())
