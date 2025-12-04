import asyncio
import logging
from copy import deepcopy

from jobs.fetch.pool_price import PoolInfoFetcherMidgard
from lib.constants import DOGE_SYMBOL
from lib.depcont import DepContainer
from models.pool_info import PoolInfo
from notify.broadcast import Broadcaster
from notify.public.pool_churn_notify import PoolChurnNotifier
from tools.lib.lp_common import LpAppFramework


async def dbg_simulate_pool_churn(d: DepContainer):
    d.broadcaster = Broadcaster(d)

    ppf = PoolInfoFetcherMidgard(d, 100)
    notifier_pool_churn = PoolChurnNotifier(d)
    notifier_pool_churn.add_subscriber(d.alert_presenter)

    ph = await d.pool_cache.get()

    await ppf.get_pool_info_midgard()

    # feed original pools
    await notifier_pool_churn.on_data(ppf, {})
    await notifier_pool_churn.on_data(ppf, ph.pool_info_map)  # must notify about changes above ^^^

    pool_info_map = deepcopy(ph.pool_info_map)  # make a copy
    del pool_info_map['ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7']  # deleted pool
    pool_info_map[DOGE_SYMBOL].status = PoolInfo.STAGED  # staged pool
    # pool_info_map[DOGE_SYMBOL] = PoolInfo(DOGE_SYMBOL, 18555, 18555, 100, PoolInfo.STAGED)

    await notifier_pool_churn.spam_cd.clear()
    # to make sure we do not notify about pool removal
    notifier_pool_churn.ignore_pool_removed = False
    await notifier_pool_churn.on_data(ppf, pool_info_map)  # no update at this moment!
    await asyncio.sleep(5)


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        
        await dbg_simulate_pool_churn(lp_app.deps)


if __name__ == '__main__':
    asyncio.run(main())
