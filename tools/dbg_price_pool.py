import asyncio
import logging

import aiohttp

logging.basicConfig(level=logging.INFO)

from services.fetch.pool_price import PoolPriceFetcher

loop = asyncio.get_event_loop()


async def test_pp():
    async with aiohttp.ClientSession() as session:
        pp = PoolPriceFetcher(session)
        r = await pp.get_historical_price('BNB.BNB', 0)
        print(r)


async def start_foos():
    await test_pp()


if __name__ == '__main__':
    loop.run_until_complete(start_foos())
