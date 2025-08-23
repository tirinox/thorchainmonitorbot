import asyncio
import json
from copy import copy
from dataclasses import Field

from api.aionode.types import ThorPool
from comm.localization.manager import BaseLocalization
from jobs.fetch.net_stats import NetworkStatisticsFetcher
from jobs.fetch.pool_price import PoolFetcher
from lib.date_utils import DAY
from lib.depcont import DepContainer
from lib.money import distort_randomly
from lib.texts import up_down_arrow
from lib.utils import load_pickle, save_pickle
from models.net_stats import NetworkStats, AlertNetworkStats
from models.node_info import NetworkNodes
from models.pool_info import PoolInfoMap, parse_thor_pools
from notify.public.stats_notify import NetworkStatsNotifier
from tools.lib.lp_common import LpAppFramework

CACHE_NET_STATS = False
CACHE_NET_STATS_FILE = '../tmp/net_stats.pickle'
NET_STATS_RANDOMIZE = False

DRY_RUN = False


def randomize_all_fields(old: NetworkStats, dev=10):
    exceptions = {'date_ts'}
    new = NetworkStats()
    # noinspection PyUnresolvedReferences
    for name, field in old.__dataclass_fields__.items():
        val = getattr(old, name)
        if name not in exceptions:
            field: Field
            if field.type in (int, float):
                val = distort_randomly(val, dev)
        setattr(new, name, val)
    return new


async def print_message(old_info: NetworkStats, new_info: NetworkStats, deps: DepContainer, nodes, loc=None):
    loc: BaseLocalization = loc or deps.loc_man.default

    message = loc.notification_text_network_summary(AlertNetworkStats(
        old_info, new_info, nodes,
    ))
    print('OLD:')
    print(old_info)
    print('-' * 100)
    print('NEW:')
    print(new_info)
    print('-' * 100)
    print(message)


def get_info_pair_for_test(new_info: NetworkStats) -> (NetworkStats, NetworkStats):
    old_info = copy(new_info)
    old_info.date_ts -= DAY
    old_info = randomize_all_fields(old_info, 10)

    return old_info, new_info


class MockPPF(PoolFetcher):
    def __init__(self, deps: DepContainer):
        super().__init__(deps)
        self.pool_name_to_delete = ''

    async def load_pools(self, height=None, caching=False, **kwargs) -> PoolInfoMap:
        with open('tools/debug/example_pools.json', 'r') as f:
            data = json.load(f)
            pool_map = parse_thor_pools([ThorPool.from_json(p) for p in data])

            if self.pool_name_to_delete in pool_map:
                del pool_map[self.pool_name_to_delete]

            return pool_map



async def demo_generic_pool_message():
    lpgen = LpAppFramework()

    new_info = load_pickle(CACHE_NET_STATS_FILE) if CACHE_NET_STATS else None

    if not new_info:
        async with lpgen:
            lpgen.deps.pool_fetcher = MockPPF(lpgen.deps)
            nsf = NetworkStatisticsFetcher(lpgen.deps)
            new_info = await nsf.fetch()

            if CACHE_NET_STATS:
                save_pickle(CACHE_NET_STATS_FILE, new_info)

    if NET_STATS_RANDOMIZE:
        old_info, new_info = get_info_pair_for_test(new_info)
    else:
        old_info = copy(new_info)

    await print_message(old_info, new_info, lpgen.deps, loc=lpgen.deps.loc_man.get_from_lang('rus'))
    await print_message(old_info, new_info, lpgen.deps, loc=lpgen.deps.loc_man.get_from_lang('eng'))


def upd(old_value, new_value, smiley=False, more_is_better=True, same_result='',
        int_delta=False, money_delta=False, percent_delta=False, signed=True,
        money_prefix=''):
    print(
        f'{old_value=}, {new_value=}, "{up_down_arrow(old_value, new_value, smiley, more_is_better, same_result, int_delta, money_delta, percent_delta, signed, money_prefix)}"')


def demo_upd():
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


async def demo_pool_stats_normal():
    app = LpAppFramework()

    async with app:
        fetcher_stats = NetworkStatisticsFetcher(app.deps)
        new_info = await fetcher_stats.fetch()

        notifier_stats = NetworkStatsNotifier(app.deps)

        await notifier_stats.notify_right_now(new_info)


async def demo_pool_stats_direct():
    app = LpAppFramework()

    async with app(brief=False):
        fetcher_stats = NetworkStatisticsFetcher(app.deps)
        new_info = await fetcher_stats.fetch()
        old_info = randomize_all_fields(new_info, 10)
        old_info.date_ts = new_info.date_ts - 2 * DAY

        nodes: NetworkNodes = await app.deps.node_cache.get()

        await app.test_all_locs(BaseLocalization.notification_text_network_summary,
                                None,
                                AlertNetworkStats(
                                    old_info,
                                    new_info,
                                    nodes.node_info_list
                                ))


async def main():
    # await demo_generic_pool_message()
    await demo_pool_stats_direct()


if __name__ == "__main__":
    # demo_upd()
    asyncio.run(main())
