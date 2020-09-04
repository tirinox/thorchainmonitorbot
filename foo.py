import asyncio

from config import Config, DB
from fetcher import InfoFetcher, ThorInfo


async def main():
    db = DB()
    await db.get_redis()

    print(ThorInfo.from_json("43"))

    cfg = Config()
    fetcher = InfoFetcher(cfg)
    j = (await fetcher.fetch_caps())

    print(j.as_json)
    i = ThorInfo.from_json(j.as_json)
    print(i)

asyncio.run(main())

