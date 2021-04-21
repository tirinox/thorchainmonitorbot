import asyncio
import logging
import os
import pickle
import random
from copy import copy
from dataclasses import dataclass, Field

from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import BaseLocalization
from services.jobs.fetch.net_stats import NetworkStatisticsFetcher
from services.lib.date_utils import DAY
from services.lib.depcont import DepContainer
from services.lib.texts import up_down_arrow
from services.lib.utils import setup_logs
from services.models.net_stats import NetworkStats
from services.notify.broadcast import Broadcaster
from tools.dbg_lp import LpTesterBase

CACHE_NET_STATS = True
CACHE_NET_STATS_FILE = '../../net_stats.pickle'

DRY_RUN = False


def randomize(x, dev=10):
    new_x = x + random.uniform(-1, 1) * abs(x / 100.0 * dev)
    return int(new_x) if isinstance(x, int) else new_x


def randomize_all_fields(old: NetworkStats, dev=10):
    exceptions = {'date_ts'}
    new = NetworkStats()
    for name, field in old.__dataclass_fields__.items():
        val = getattr(old, name)
        if name not in exceptions:
            field: Field
            if field.type in (int, float):
                val = randomize(val, dev)
        setattr(new, name, val)
    return new



async def print_message(new_info: NetworkStats, deps: DepContainer):
    old_info = copy(new_info)
    old_info.date_ts -= DAY
    old_info = randomize_all_fields(old_info, 10)

    loc: BaseLocalization = deps.loc_man.default
    message = loc.notification_text_network_summary(old_info, new_info)
    print('OLD:')
    print(old_info)
    print('NEW:')
    print(new_info)
    print('-' * 100)
    print(message)

    if not DRY_RUN:
        deps.loop = asyncio.get_event_loop()
        deps.bot = Bot(token=deps.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
        deps.dp = Dispatcher(deps.bot, loop=deps.loop)
        deps.broadcaster = Broadcaster(deps)
        await deps.broadcaster.notify_preconfigured_channels(
            deps.loc_man,
            loc.notification_text_network_summary,
            old_info, new_info)
        await asyncio.sleep(1.0)


async def main():
    lpgen = LpTesterBase()

    if CACHE_NET_STATS and os.path.exists(CACHE_NET_STATS_FILE):
        with open(CACHE_NET_STATS_FILE, 'rb') as f:
            new_info = pickle.load(f)
    else:
        async with lpgen:
            nsf = NetworkStatisticsFetcher(lpgen.deps, lpgen.ppf)
            new_info = await nsf.fetch()

            if CACHE_NET_STATS:
                with open(CACHE_NET_STATS_FILE, 'wb') as f:
                    pickle.dump(new_info, f)

    await print_message(new_info, lpgen.deps)


def upd(old_value, new_value, smiley=False, more_is_better=True, same_result='',
        int_delta=False, money_delta=False, percent_delta=False, signed=True,
        money_prefix=''):
    print(
        f'{old_value=}, {new_value=}, "{up_down_arrow(old_value, new_value, smiley, more_is_better, same_result, int_delta, money_delta, percent_delta, signed, money_prefix)}"')


if __name__ == "__main__":
    upd(10, 10)
    upd(10, 15, int_delta=True, smiley=True)
    upd(10, 15, int_delta=True)
    upd(100, 90, int_delta=True, smiley=True)
    upd(100_000_000, 90_200_000, money_delta=True, smiley=True)
    upd(100, 110, percent_delta=True, smiley=True)
    upd(100, 90, percent_delta=True, smiley=True)
    upd(100, 200, percent_delta=True, smiley=True)
    upd(23, 25, int_delta=True, more_is_better=False)
    upd(20, 10, int_delta=True, more_is_better=False, signed=False)
    upd(0, 10, int_delta=True, more_is_better=False, signed=False)  # no old = ignore

    setup_logs(logging.INFO)
    asyncio.run(main())
