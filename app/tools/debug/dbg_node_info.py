import asyncio
import logging

from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.utils import setup_logs
from tools.lib.lp_common import LpAppFramework


async def main():
    lpgen = LpAppFramework()
    async with lpgen:
        node_info_fetcher = NodeInfoFetcher(lpgen.deps)
        result = await node_info_fetcher.fetch()
        print(result)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
