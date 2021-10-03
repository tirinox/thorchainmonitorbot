import asyncio
import logging

import aiohttp

from services.jobs.fetch.runeyield.external import get_user_pools_from_thoryield
from services.lib.utils import setup_logs


async def main():
    async with aiohttp.ClientSession() as session:
        r = await get_user_pools_from_thoryield(session, 'bnb1p7cp6kv3am46eagg40lqls9lfpsk8tf3aqffj0')
        print(r)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
