import asyncio
import logging

from services.jobs.fetch.chains import ChainStateFetcher
from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework(log_level=logging.WARNING)
    async with app(brief=True):
        fetcher_chain_state = ChainStateFetcher(app.deps)
        data = await fetcher_chain_state.fetch()
        print(data)


if __name__ == '__main__':
    asyncio.run(main())
