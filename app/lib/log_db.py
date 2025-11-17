import asyncio
import json

from lib.db import DB


class RedisLog:
    def __init__(self, prefix: str, db: DB, max_lines=10_000):
        self.prefix = prefix
        self.db = db
        self.max_lines = max_lines

    @property
    def db_key(self):
        return f'{self.prefix}:Logs'

    async def add_log(self, data: dict):
        data['_ts'] = asyncio.get_event_loop().time()
        payload = json.dumps(data)

        pipe = self.db.redis.pipeline()
        await pipe.rpush(self.db_key, payload)
        # keep last max_lines elements
        await pipe.ltrim(self.db_key, -self.max_lines, -1)
        await pipe.execute()

    async def get_last_logs(self, count=100):
        entries = await self.db.redis.lrange(self.db_key, -count, -1)
        items = [json.loads(entry) for entry in entries]
        items.sort(key=lambda x: x.get('_ts', 0))
        return items
