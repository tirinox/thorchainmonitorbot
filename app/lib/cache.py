import json

from web3.datastructures import AttributeDict

from lib.db import DB


class Web3TxEncoder(json.JSONEncoder):
    def default(self, z):
        if isinstance(z, bytes):
            return z.hex()
        elif isinstance(z, AttributeDict):
            return dict(z)
        else:
            return super().default(z)


class Cache:
    def __init__(self, db: DB, name):
        self.db = db
        self.name = name

    def load_transform(self, data):
        return json.loads(data) if data else None

    def save_transform(self, data):
        if isinstance(data, AttributeDict):
            data = dict(data)
        if not isinstance(data, str):
            data = json.dumps(data, cls=Web3TxEncoder)
        return data

    async def load(self, key):
        data = await self.db.redis.hget(self.name, key)
        return self.load_transform(data)

    async def store(self, key, data):
        if key:
            data = self.save_transform(data)
            await self.db.redis.hset(self.name, key, data)

    async def clear(self):
        await self.db.redis.delete(self.name)


class CacheNamedTuple(Cache):
    def __init__(self, db: DB, name, tuple_class: type):
        self.tuple_class = tuple_class
        super().__init__(db, name)

    def load_transform(self, data):
        data = super(CacheNamedTuple, self).load_transform(data)
        try:
            # noinspection PyArgumentList
            data = self.tuple_class(**data)
        except TypeError:
            # apparently the format has changed, so reload and save it again
            data = None
        return data

    def save_transform(self, data):
        # noinspection PyProtectedMember
        return super(CacheNamedTuple, self).save_transform(data._asdict())
