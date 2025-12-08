import asyncio
import logging

from jobs.price_recorder import PriceRecorder
from lib.date_utils import DAY
from tools.lib.lp_common import LpAppFramework

INTERVAL = 5 * DAY
POOL_PRICE_THRESHOLD = 11.0
DET_PRICE_THRESHOLD = 2.0


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare

        price_recorder = PriceRecorder(lp_app.deps.db)
        await price_recorder.purge_spikes(INTERVAL,
                                          max_value_det=DET_PRICE_THRESHOLD, max_value_pool=POOL_PRICE_THRESHOLD)


if __name__ == '__main__':
    asyncio.run(main())
