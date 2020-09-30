import aioredis
import yaml
import sys
import os
from prodict import Prodict
from dotenv import load_dotenv

load_dotenv()


class Config(Prodict):
    DEFAULT = 'config.yaml'

    def __init__(self):
        self._config_name = sys.argv[1] if len(sys.argv) >= 2 else self.DEFAULT
        with open(self._config_name, 'r') as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)
        super().__init__(**data)


class DB:
    def __init__(self, loop):
        self.loop = loop
        self.redis: aioredis.Redis = None

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is not None:
            return self.redis
        host = os.environ.get('REDIS_HOST', 'localhost')
        port = os.environ.get('REDIS_PORT', 6382)
        password = os.environ.get('REDIS_PASSWORD', None)
        redis = await aioredis.create_redis(
            f'redis://{host}:{port}',
            password=password,
            loop=self.loop)
        self.redis = redis
        return redis

    async def close_redis(self):
        self.redis.close()
        await self.redis.wait_closed()
