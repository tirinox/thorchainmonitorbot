import asyncio
import json
import logging
import random
from copy import copy
from dataclasses import Field

from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiothornode.types import ThorPool

from localization import BaseLocalization
from services.jobs.fetch.net_stats import NetworkStatisticsFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.date_utils import DAY
from services.lib.depcont import DepContainer
from services.lib.texts import up_down_arrow
from services.lib.utils import setup_logs, load_pickle, save_pickle
from services.models.net_stats import NetworkStats
from services.models.pool_info import PoolInfoMap, parse_thor_pools
from services.notify.broadcast import Broadcaster
from tools.lib.lp_common import LpAppFramework

CACHE_NET_STATS = True
CACHE_NET_STATS_FILE = '../../tmp/net_stats.pickle'

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


async def print_message(old_info: NetworkStats, new_info: NetworkStats, deps: DepContainer, post_tg=True):
    loc: BaseLocalization = deps.loc_man.default
    message = loc.notification_text_network_summary(old_info, new_info)
    print('OLD:')
    print(old_info)
    print('-' * 100)
    print('NEW:')
    print(new_info)
    print('-' * 100)
    print(message)

    if not DRY_RUN and post_tg:
        deps.loop = asyncio.get_event_loop()
        deps.bot = Bot(token=deps.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
        deps.dp = Dispatcher(deps.bot, loop=deps.loop)
        deps.broadcaster = Broadcaster(deps)
        await deps.broadcaster.notify_preconfigured_channels(
            deps.loc_man,
            loc.notification_text_network_summary,
            old_info, new_info)
        await asyncio.sleep(1.0)


def get_info_pair_for_test(new_info: NetworkStats) -> (NetworkStats, NetworkStats):
    old_info = copy(new_info)
    old_info.date_ts -= DAY
    old_info = randomize_all_fields(old_info, 10)

    return old_info, new_info


class MockPPF(PoolPriceFetcher):
    def __init__(self, deps: DepContainer):
        super().__init__(deps)
        self.pool_name_to_delete = ''

    async def get_current_pool_data_full(self, height=None, caching=False) -> PoolInfoMap:
        with open('tools/debug/example_pools.json', 'r') as f:
            data = json.load(f)
            pool_map = parse_thor_pools([ThorPool.from_json(p) for p in data])

            if self.pool_name_to_delete in pool_map:
                del pool_map[self.pool_name_to_delete]

            return pool_map


async def test_pool_consistency():
    lpgen = LpAppFramework()

    async with lpgen:
        # 1. new_info is from JSON file (contains just pool list)
        ppf_mock = lpgen.deps.price_pool_fetcher = MockPPF(lpgen.deps)
        nsf = NetworkStatisticsFetcher(lpgen.deps)
        new_info = await nsf.fetch()

        # 2. remove on of the pools, HEGIC e.g
        ppf_mock.pool_name_to_delete = 'ETH.HEGIC-0X584BC13C7D411C00C01A62E8019472DE68768430'

        # 3. new info has 1 less pending pools
        old_info = await nsf.fetch()

        assert old_info.pending_pool_count == 5
        assert new_info.pending_pool_count == 6

    await print_message(old_info, new_info, lpgen.deps, post_tg=False)


async def test_generic_pool_message():
    lpgen = LpAppFramework()

    new_info = load_pickle(CACHE_NET_STATS_FILE) if CACHE_NET_STATS else None

    if not new_info:
        async with lpgen:
            lpgen.deps.price_pool_fetcher = MockPPF(lpgen.deps)
            nsf = NetworkStatisticsFetcher(lpgen.deps)
            new_info = await nsf.fetch()

            if CACHE_NET_STATS:
                save_pickle(CACHE_NET_STATS_FILE, new_info)

    old_info, new_info = get_info_pair_for_test(new_info)

    await print_message(old_info, new_info, lpgen.deps)


def upd(old_value, new_value, smiley=False, more_is_better=True, same_result='',
        int_delta=False, money_delta=False, percent_delta=False, signed=True,
        money_prefix=''):
    print(
        f'{old_value=}, {new_value=}, "{up_down_arrow(old_value, new_value, smiley, more_is_better, same_result, int_delta, money_delta, percent_delta, signed, money_prefix)}"')


def test_upd():
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


async def main():
    await test_pool_consistency()


if __name__ == "__main__":
    # test_upd()
    setup_logs(logging.INFO)
    asyncio.run(main())