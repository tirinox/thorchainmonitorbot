import json

import aioredis
import yaml
import sys
import os
from prodict import Prodict

from model import ThorInfo


class Config(Prodict):
    DEFAULT = 'config.yaml'

    def __init__(self):
        self._config_name = sys.argv[1] if len(sys.argv) >= 2 else self.DEFAULT
        with open(self._config_name, 'r') as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)
        super().__init__(**data)


class DB:
    KEY_USERS = 'thbot_users'
    KEY_INFO = 'th_info'
    KEY_ATH = 'th_ath_rune_price'

    def __init__(self):
        self.redis: aioredis.Redis = None

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is not None:
            return self.redis
        host = os.environ.get('REDIS_HOST', 'localhost')
        port = os.environ.get('REDIS_PORT', 6379)
        password = os.environ.get('REDIS_PASSWORD', None)
        redis = await aioredis.create_redis(
            f'redis://{host}:{port}',
            password=password)
        self.redis = redis
        return redis

    async def close_redis(self):
        self.redis.close()
        await self.redis.wait_closed()

    # -- users --

    async def add_user(self, ident):
        ident = str(int(ident))
        r = await self.get_redis()
        await r.sadd(self.KEY_USERS, ident)

    async def remove_users(self, idents):
        idents = [str(int(i)) for i in idents]
        if idents:
            r = await self.get_redis()
            await r.srem(self.KEY_USERS, *idents)

    async def all_users(self):
        r = await self.get_redis()
        items = await r.smembers(self.KEY_USERS)
        return [int(it) for it in items]

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
