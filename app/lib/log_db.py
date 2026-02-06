import datetime
import json

from lib.db import DB
from lib.logs import WithLogger


class CircularLog(WithLogger):
    def __init__(self, prefix: str, db: DB, max_lines=10_000):
        super().__init__()
        self.prefix = prefix
        self.db = db
        self.max_lines = max_lines

    @property
    def db_key(self):
        return f'{self.prefix}:Logs'

    async def add_log(self, data: dict):
        data['_ts'] = datetime.datetime.now().timestamp()
        payload = json.dumps(data)

        pipe = self.db.redis.pipeline()
        await pipe.rpush(self.db_key, payload)
        # keep last max_lines elements
        await pipe.ltrim(self.db_key, -self.max_lines, -1)
        await pipe.execute()

    async def get_last_logs(self, count=100):
        entries = await self.db.redis.lrange(self.db_key, -count, -1)
        items = [json.loads(entry) for entry in entries]
        items.sort(key=lambda x: -x.get('_ts', 0))
        return items

    async def add_log_safe(self, name, level, **kwargs):
        try:
            await self.add_log({
                'level': level,
                'action': name,
                **kwargs,
            })
        except Exception as e:
            self.logger.error(f'Failed to add log entry: {e}')

    async def info(self, name, **kwargs):
        await self.add_log_safe(name, level='info', **kwargs)

    async def error(self, name, **kwargs):
        await self.add_log_safe(name, level='error', **kwargs)

    async def warning(self, name, **kwargs):
        await self.add_log_safe(name, level='warning', **kwargs)
