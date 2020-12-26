import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import LocalizationManager
from services.dialog.queue_picture import QUEUE_TIME_SERIES
from services.lib.config import Config
from services.lib.cooldown import Cooldown
from services.lib.datetime import DAY
from services.lib.db import DB
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.depcont import DepContainer
from services.lib.money import pretty_money
from services.models.time_series import TimeSeries
from services.models.tx import StakePoolStats
from services.notify.broadcast import Broadcaster
from services.lib.texts import progressbar

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

deps = DepContainer()
deps.cfg = Config()

log_level = deps.cfg.get('log_level', logging.INFO)

logging.basicConfig(level=logging.getLevelName(log_level))
logging.info(f"Log level: {log_level}")

deps.loop = asyncio.get_event_loop()
deps.db = DB(deps.loop)

deps.bot = Bot(token=deps.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
deps.dp = Dispatcher(deps.bot, loop=deps.loop)
deps.loc_man = LocalizationManager()
deps.broadcaster = Broadcaster(deps)

lock = asyncio.Lock()


async def mock_broadcaster(tag, n, delay=0.2):
    async with lock:
        for i in range(n):
            print(f'mock_broadcaster : {tag} step {i}')
            await asyncio.sleep(delay)


async def foo15():
    series = []
    x = 10
    while x < 1_000_000_000:
        p = StakePoolStats.curve_for_tx_threshold(x)
        abs_th = x * p
        series.append((x, p, abs_th))
        print(f'{x},{p:.2f},{(x * p):.0f}')
        x *= 1.3
    series = pd.DataFrame(series, columns=['pool_depth_usd', 'percent', 'threshold_usd'])

    f, ax = plt.subplots(figsize=(7, 7))

    sns.set_theme()
    sns.lineplot(data=series, x='pool_depth_usd', y='threshold_usd', ax=ax)
    # sns.lineplot(data=series, x='pool_depth_usd', y='percent', ax=ax)
    ax.set(xscale="log", yscale='log')
    ax.grid()
    plt.show()


async def foo2():
    await asyncio.gather(mock_broadcaster('first', 10, 0.2), mock_broadcaster('second', 12, 0.1))


async def foo12():
    print(progressbar(0, 100, 30))
    print(progressbar(-14, 100, 30))
    print(progressbar(10, 100, 30))
    print(progressbar(1200, 100, 30))
    await StakePoolStats.clear_all_data(deps.db)


async def foo13():
    async with aiohttp.ClientSession() as deps.session:
        deps.thor_man = ThorNodeAddressManager(deps.cfg.thornode.seed, deps.session)
        ppf = PoolPriceFetcher(deps)
        data = await ppf.get_current_pool_data_full()
    print(data)


async def test_cd_mult():
    cd = Cooldown(deps.db, 'test-event', 3, max_times=2)
    assert await cd.can_do()
    await cd.do()
    assert await cd.can_do()
    await cd.do()
    assert not await cd.can_do()
    await cd.do()
    assert not await cd.can_do()
    await asyncio.sleep(3.5)
    assert await cd.can_do()
    await cd.do()
    assert await cd.can_do()
    await cd.do()
    await asyncio.sleep(2.5)
    assert not await cd.can_do()
    await asyncio.sleep(1.0)
    assert await cd.can_do()
    print('Done')


async def foo16(d):
    ts = TimeSeries(QUEUE_TIME_SERIES, d.db)
    avg = await ts.average(DAY, 'outbound_queue')
    print(avg)


async def start_foos():
    await deps.db.get_redis()
    # await test_cd_mult()
    await foo16(deps)


if __name__ == '__main__':
    deps.loop.run_until_complete(start_foos())
