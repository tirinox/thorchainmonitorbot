import asyncio
import logging

from services.jobs.fetch.thormon import ThorMonWSSClient, ThorMonSolvencyFetcher
from tools.lib.lp_common import LpAppFramework


async def test_wss():
    logging.basicConfig(level=logging.DEBUG)
    client = ThorMonWSSClient('mainnet')
    await client.listen_forever()


async def test_solvency():
    lp_app = LpAppFramework()
    async with lp_app:
        fetcher = ThorMonSolvencyFetcher(lp_app.deps)
        data = await fetcher.fetch()
        print(data)


async def main():
    # await test_solvency()
    await test_wss()


if __name__ == '__main__':
    asyncio.run(main())
