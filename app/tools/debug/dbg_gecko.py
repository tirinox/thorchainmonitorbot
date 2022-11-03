import asyncio
import logging

from services.jobs.fetch.gecko_price import get_thorchain_coin_gecko_info
from services.lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app():
        sep()
        await asyncio.sleep(2.0)
        r = await get_thorchain_coin_gecko_info(lp_app.deps.session)
        print(r)
        print('done')


if __name__ == '__main__':
    asyncio.run(main())
