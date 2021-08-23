import asyncio
import logging

from services.jobs.fetch.thormon import ThormonWSSClient


async def main():
    logging.basicConfig(level=logging.DEBUG)
    client = ThormonWSSClient()
    await client.listen_forever()


if __name__ == '__main__':
    asyncio.run(main())
