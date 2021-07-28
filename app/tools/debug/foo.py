import asyncio
import json
import logging
import os
import random

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
from services.jobs.fetch.gecko_price import get_thorchain_coin_gecko_info
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.tx import TxFetcher
from services.lib.config import Config
from services.lib.constants import *
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import MidgardParserV2
from services.lib.money import pretty_money
from services.lib.telegram import telegram_send_message_basic, TG_TEST_USER
from services.lib.texts import progressbar
from services.lib.utils import sep
from services.models.cap_info import ThorCapInfo
from services.models.node_info import NodeSetChanges, NodeInfo
from services.models.pool_info import PoolChange, PoolChanges, PoolInfo
from services.models.pool_stats import LiquidityPoolStats
from services.models.time_series import TimeSeries
from services.models.tx import ThorTxExtended
from services.notify.broadcast import Broadcaster

TG_USER = TG_TEST_USER
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


async def foo21():
    c = NodeSetChanges(
        nodes_added=[],
        nodes_removed=[NodeInfo.fake_node()],
        nodes_deactivated=[],
        nodes_activated=[],
        nodes_all=[],
        nodes_previous=[]
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
    changes1 = [
        ThorChainInfo(chain='BNB', halted=True),
        ThorChainInfo(chain='BTC', halted=True),
        ThorChainInfo(chain='ETH', halted=True),
    ]

    changes2 = [
        ThorChainInfo(chain='BNB', halted=False),
        ThorChainInfo(chain='BTC', halted=False),
        ThorChainInfo(chain='ETH', halted=False),
    ]

    for loc in (loc_ru, loc_en):
        text = loc.notification_text_trading_halted_multi(changes1)
        print(text)
        sep()
        await telegram_send_message_basic(TG_TOKEN, TG_USER, text)

        sep()

        text = loc.notification_text_trading_halted_multi(changes2)
        print(text)
        sep()
        await telegram_send_message_basic(TG_TOKEN, TG_USER, text)

        sep()

        text = loc.notification_text_trading_halted_multi(changes2 + changes1)
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


async def foo28_gecko_cex_volume():
    data = await get_thorchain_coin_gecko_info(deps.session)
    print(data)


def load_sample_tx(filename):
    samples = './tests/tx_examples'
    with open(os.path.join(samples, filename), 'r') as f:
        data = json.load(f)

    p = MidgardParserV2(network_id=NetworkIdents.CHAOSNET_MULTICHAIN)
    txs = p.parse_tx_response(data).txs
    return txs


async def eval_notifications(txs, locs=None, send_to_tg=False, usd_per_rune=4.0, pool=BTC_SYMBOL):
    locs = locs or (loc_en, loc_ru)

    pool_info = PoolInfo(pool, 100000000, 323434434343, 76767654554, PoolInfo.AVAILABLE)

    for tx in txs:
        tx_ex = ThorTxExtended.load_from_thor_tx(tx)
        tx_ex.calc_full_rune_amount(pool_info.asset_per_rune)

        for loc in locs:
            print(f"{loc = }.")
            text = loc.notification_text_large_tx(tx_ex, usd_per_rune, pool_info)
            print(text)
            sep()
            if send_to_tg:
                await telegram_send_message_basic(TG_TOKEN, TG_USER, text)


async def foo29_donate_notification():
    txs = load_sample_tx('v2_donate.json')
    await eval_notifications(txs[:1], send_to_tg=True)


async def foo30_swap_notification():
    txs = load_sample_tx('v2_swap.json')
    await eval_notifications(txs[:1], send_to_tg=True)


async def foo31_switch_notification():
    txs = load_sample_tx('v2_switch.json')
    await eval_notifications(txs[:1], send_to_tg=True)


async def foo32_refund_notification():
    txs = load_sample_tx('v2_refund_multi.json')
    await eval_notifications(txs, send_to_tg=False, locs=(loc_en,))

    sep(space=True)

    txs = load_sample_tx('v2_refund.json')
    await eval_notifications(txs, send_to_tg=False, locs=(loc_en,))


async def foo33_many_sub_tx():
    txs = load_sample_tx('v2_refund_multi.json')
    tx = txs[0]
    tx.out_tx += [tx.out_tx[0]] * 3
    await eval_notifications([tx], send_to_tg=True)


async def foo34_swap_test_notification():
    txs = load_sample_tx('v2_swap.json')
    await eval_notifications(txs, send_to_tg=False, locs=[loc_en])


async def start_foos():
    async with aiohttp.ClientSession() as deps.session:
        deps.thor_connector = ThorConnector(get_thor_env_by_network_id(deps.cfg.network_id), deps.session)
        await deps.db.get_redis()
        # await foo29_donate_notification()
        # await foo30_swap_notification()
        await foo34_swap_test_notification()


if __name__ == '__main__':
    deps.loop.run_until_complete(start_foos())
