import json

import aioredis
import yaml
import sys
import os
from prodict import Prodict
from dotenv import load_dotenv

from services.fetch.model import ThorInfo


load_dotenv()


class Config(Prodict):
    DEFAULT = 'config.yaml'

    def __init__(self):
        self._config_name = sys.argv[1] if len(sys.argv) >= 2 else self.DEFAULT
        with open(self._config_name, 'r') as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)
        super().__init__(**data)


class DB:
    KEY_INFO = 'th_info'
    KEY_ATH = 'th_ath_rune_price'

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

    # -- ath --

    async def get_ath(self):
        try:
            return float(await self.redis.get(self.KEY_ATH))
        except (TypeError, ValueError, AttributeError):
            return 0.0

    async def update_ath(self, price):
        ath = await self.get_ath()
        if price > ath:
            await self.redis.set(self.KEY_ATH, price)
            return True
        return False

    # -- caps --

    async def get_old_cap(self):
        try:
            return ThorInfo.from_json(await self.redis.get(self.KEY_INFO))
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            return ThorInfo.zero()

    async def set_cap(self, info: ThorInfo):
        if self.redis:
            await self.redis.set(self.KEY_INFO, info.as_json)
