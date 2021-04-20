import asyncio
import logging
import os
import pickle
from copy import copy

from localization import BaseLocalization
from services.jobs.fetch.net_stats import NetworkStatisticsFetcher
from services.lib.date_utils import DAY
from services.lib.utils import setup_logs
from services.models.net_stats import NetworkStats
from tools.dbg_lp import LpTesterBase

CACHE_NET_STATS = True
CACHE_NET_STATS_FILE = '../../net_stats.pickle'


async def print_message(new_info: NetworkStats, loc: BaseLocalization):
    old_info = copy(new_info)
    old_info.date_ts -= DAY

    message = loc.notification_text_network_summary(old_info, new_info)
    print('-' * 100)
    print(message)


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

    await print_message(new_info, lpgen.deps.loc_man.default)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
