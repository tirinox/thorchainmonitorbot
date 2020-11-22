import asyncio
import logging

import aiohttp

from services.fetch.node_ip_manager import ThorNodeAddressManager


async def main():
    async with aiohttp.ClientSession() as session:
        thor_man = ThorNodeAddressManager(session)
        node = await thor_man.select_node()
        print(node)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
