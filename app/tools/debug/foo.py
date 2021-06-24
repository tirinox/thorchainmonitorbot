import asyncio
import logging
import random
import secrets

import aiohttp
import sha3
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiothornode.connector import ThorConnector
from aiothornode.types import ThorChainInfo
from pycoingecko import CoinGeckoAPI

from localization import LocalizationManager
from services.dialog.picture.crypto_logo import CryptoLogoDownloader
from services.dialog.picture.queue_picture import QUEUE_TIME_SERIES
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.tx import TxFetcher
from services.lib.config import Config
from services.lib.constants import *
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY, now_ts
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.money import pretty_money
from services.lib.telegram import telegram_send_message_basic
from services.lib.texts import progressbar
from services.models.cap_info import ThorCapInfo
from services.models.node_info import NodeInfoChanges, NodeInfo
from services.models.pool_info import PoolChange, PoolChanges, PoolInfo
from services.models.pool_stats import LiquidityPoolStats
from services.models.time_series import TimeSeries
from services.models.tx import LPAddWithdrawTx, ThorTxType
from services.notify.broadcast import Broadcaster

TG_USER = 192398802
SEND_TO_TG = True

deps = DepContainer()
deps.cfg = Config()

log_level = deps.cfg.get_pure('log_level', logging.INFO)

logging.basicConfig(level=logging.getLevelName(str(log_level)))
logging.info(f"Log level: {log_level}")

deps.loop = asyncio.get_event_loop()
deps.db = DB(deps.loop)

deps.bot = Bot(token=deps.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
deps.dp = Dispatcher(deps.bot, loop=deps.loop)
deps.loc_man = LocalizationManager(deps.cfg)
deps.broadcaster = Broadcaster(deps)

lock = asyncio.Lock()

TG_TOKEN = str(deps.cfg.get('telegram.bot.token'))

loc_man: LocalizationManager = deps.loc_man
loc_ru = loc_man.get_from_lang('rus')
loc_en = loc_man.get_from_lang('eng')


def sep():
    print('-' * 100)


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
    await LiquidityPoolStats.clear_all_data(deps.db)


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


async def foo16():
    ts = TimeSeries(QUEUE_TIME_SERIES, deps.db)
    avg = await ts.average(DAY, 'outbound_queue')
    print(avg)


async def foo17():
    txf = TxFetcher(deps)
    # await txf.clear_all_seen_tx()
    r = await txf.fetch()
    print(r)
    # for tx in r:
    #     tx: ThorTx
    #     await txf.add_last_seen_tx(tx.tx_hash)
    ...


async def foo18():
    # print(today_str())
    money = 524
    while money > 1e-8:
        print(pretty_money(money))
        money *= 0.1


async def foo19():
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


async def foo20():
    eth_address = '234'
    print(sha3.keccak_256(eth_address.encode('utf-8')).hexdigest())
    print('0xc1912fee45d61c87cc5ea59dae311904cd86b84fee17cc96966216f811ce6a79')
    print('0xbc36789e7a1e281436464229828f817d6612f7b477d66591ff96a9e064bcc98a')


def fake_node(status=NodeInfo.ACTIVE, address=None, bond=None, ip=None, version='54.1', slash=0):
    r = lambda: random.randint(1, 255)
    ip = ip if ip is not None else f'{r()}.{r()}.{r()}.{r()}'
    address = address if address is not None else f'thor{secrets.token_hex(32)}'
    bond = bond if bond is not None else random.randint(1, 2_000_000)
    return NodeInfo(status, address, bond, ip, version, slash)


async def foo21():
    c = NodeInfoChanges(
        nodes_added=[],
        nodes_removed=[fake_node()],
        nodes_deactivated=[],
        nodes_activated=[],
        nodes_all=[]
    )

    print(loc_ru.notification_text_for_node_churn(c))


async def foo22():
    pc = PoolChanges(pools_added=[],
                     pools_removed=[],
                     pools_changed=[
                         PoolChange('ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7', PoolInfo.STAGED,
                                    PoolInfo.DEPRECATED_ENABLED),
                         PoolChange('DOGE.DOGE', PoolInfo.DEPRECATED_ENABLED, PoolInfo.STAGED)
                     ])
    for loc in (loc_ru, loc_en):
        sep()
        print(loc.notification_text_pool_churn(pc))

    sep()

    pc = PoolChanges(pools_added=[PoolChange('DOGE.DOGE', PoolInfo.DEPRECATED_ENABLED, PoolInfo.STAGED)],
                     pools_removed=[],
                     pools_changed=[])

    for loc in (loc_ru, loc_en):
        sep()
        print(loc.notification_text_pool_churn(pc))


async def foo23_tx_msg():
    add_tx = LPAddWithdrawTx(
        int(now_ts()),
        ThorTxType.TYPE_ADD_LIQUIDITY,
        'FOO',
        '123000000BB',
        '456000000AA',
        '11BBCC',
        '22DDEE',
        50.0,
        100.0,
        '88EE88',
        200.0,
        0.5,
        None
    )

    withdraw_tx = LPAddWithdrawTx(
        int(now_ts()),
        ThorTxType.TYPE_WITHDRAW,
        'FOO',
        '123000000BB',
        '456000000AA',
        '11BBCC',
        '22DDEE',
        50.0,
        100.0,
        '88EE88',
        200.0,
        0.5,
        None
    )

    tx_pool_factor = 1000  # tx is percent of pool

    pool_info = PoolInfo(
        'FOO',
        balance_asset=5_000_000_0 * tx_pool_factor,
        balance_rune=10_000_000_0 * tx_pool_factor,
        pool_units=2_000_000_000_000,
        status=PoolInfo.AVAILABLE
    )

    # pool_info = None

    cap = ThorCapInfo(
        5_500_500, 5_234_000, 9.21
    )

    for loc in (loc_ru, loc_en):
        text1 = loc.notification_text_large_tx(add_tx, 10.0, pool_info, cap)
        text2 = loc.notification_text_large_tx(withdraw_tx, 10.0, pool_info, cap)

        sep()
        print(text1)
        sep()
        print(text2)
        sep()
        msg = text1 + "\n\n" + text2
        await telegram_send_message_basic(TG_TOKEN, TG_USER, msg)


async def foo24_cap_limit():
    cap = ThorCapInfo(
        5_500_500, 5_499_100, 9.21
    )

    for loc in (loc_ru, loc_en):
        text = loc.notification_text_cap_full(cap)
        print(text)
        sep()
        await telegram_send_message_basic(TG_TOKEN, TG_USER, text)


async def foo25_coingecko_test():
    cg = CoinGeckoAPI()
    r = cg.get_price(ids=['thorchain'], vs_currencies='usd')
    print(r)


async def foo26_trading_halt_text():
    ch = ThorChainInfo(
        chain='BNB',
        halted=True
    )

    for loc in (loc_ru, loc_en):
        ch.halted = True
        text = loc.notification_text_trading_halted(ch)
        print(text)
        sep()
        await telegram_send_message_basic(TG_TOKEN, TG_USER, text)

        sep()

        ch.halted = False
        text = loc.notification_text_trading_halted(ch)
        print(text)
        sep()
        await telegram_send_message_basic(TG_TOKEN, TG_USER, text)


async def foo27_mimir_message():
    # cmf = ConstMimirFetcher(deps)
    # await cmf.fetch()

    changes = [
        # (change_type, const_name, old_value, new_value)
        ('+', 'monalled', 10, 20),
        ('+', 'purgrotabile', None, 777),
        ('-', 'offectinhow', 90, 80),
        ('-', 'pestritenda', 10, None),
        ('~', 'frivessile', 999, 1888),
        ('~', 'deouslate', 'text', 'another'),
    ]

    for loc in (loc_ru, loc_en):
    # for loc in (loc_en,):
        text = loc.notification_text_mimir_changed(changes)
        print(text)
        sep()
        await telegram_send_message_basic(TG_TOKEN, TG_USER, text)


async def start_foos():
    async with aiohttp.ClientSession() as deps.session:
        deps.thor_connector = ThorConnector(get_thor_env_by_network_id(deps.cfg.network_id), deps.session)
        await deps.db.get_redis()
        await foo27_mimir_message()


if __name__ == '__main__':
    deps.loop.run_until_complete(start_foos())
