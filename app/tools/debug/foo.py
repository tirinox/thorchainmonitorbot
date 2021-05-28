import asyncio
import logging

import aiohttp
import sha3
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiothornode.connector import ThorConnector

from localization import LocalizationManager
from services.dialog.picture.crypto_logo import CryptoLogoDownloader
from services.dialog.picture.queue_picture import QUEUE_TIME_SERIES
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.tx import TxFetcher
from services.lib.config import Config
from services.lib.constants import *
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.money import pretty_money
from services.lib.texts import progressbar
from services.models.pool_stats import StakePoolStats
from services.models.time_series import TimeSeries
from services.notify.broadcast import Broadcaster

deps = DepContainer()
deps.cfg = Config()

log_level = deps.cfg.get_pure('log_level', logging.INFO)

logging.basicConfig(level=logging.getLevelName(log_level))
logging.info(f"Log level: {log_level}")

deps.loop = asyncio.get_event_loop()
deps.db = DB(deps.loop)

deps.bot = Bot(token=deps.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
deps.dp = Dispatcher(deps.bot, loop=deps.loop)
deps.loc_man = LocalizationManager(deps.cfg)
deps.broadcaster = Broadcaster(deps)

lock = asyncio.Lock()


async def mock_broadcaster(tag, n, delay=0.2):
    async with lock:
        for i in range(n):
            print(f'mock_broadcaster : {tag} step {i}')
            await asyncio.sleep(delay)


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
        deps.thor_connector = ThorConnector(TEST_NET_ENVIRONMENT_MULTI_1.copy(), deps.session)
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


async def foo17(d):
    txf = TxFetcher(d)
    # await txf.clear_all_seen_tx()
    r = await txf.fetch()
    print(r)
    # for tx in r:
    #     tx: ThorTx
    #     await txf.add_last_seen_tx(tx.tx_hash)
    ...


async def foo18(d):
    # print(today_str())
    money = 524
    while money > 1e-8:
        print(pretty_money(money))
        money *= 0.1


async def foo19(d):
    dl = CryptoLogoDownloader('./data')
    assets = [
        # 'LTC.LTC',
        # 'ETH.ETH',
        # BNB_ETHB_SYMBOL,
        # BNB_BTCB_SYMBOL,
        # ETH_USDT_SYMBOL,
        # ETH_RUNE_SYMBOL_TEST,
        # ETH_RUNE_SYMBOL,
        ETH_USDT_TEST_SYMBOL,
    ]
    for asset in assets:
        pic = await dl.get_or_download_logo_cached(asset)
        pic.show()


async def foo20(d):
    eth_address = '234'
    print(sha3.keccak_256(eth_address.encode('utf-8')).hexdigest())
    print('0xc1912fee45d61c87cc5ea59dae311904cd86b84fee17cc96966216f811ce6a79')
    print('0xbc36789e7a1e281436464229828f817d6612f7b477d66591ff96a9e064bcc98a')


async def start_foos():
    async with aiohttp.ClientSession() as deps.session:
        await deps.db.get_redis()
        await foo19(deps)


if __name__ == '__main__':
    deps.loop.run_until_complete(start_foos())