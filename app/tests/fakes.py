from collections import defaultdict
from fnmatch import fnmatch

from models.pool_info import PoolInfo
from models.price import PriceHolder


class FakeRedis:
    def __init__(self):
        self.hashes = defaultdict(dict)
        self.strings = {}
        self.values = self.strings
        self.expirations = {}
        self.hll = defaultdict(set)

    async def hincrbyfloat(self, name, key, value):
        bucket = self.hashes[name]
        bucket[key] = float(bucket.get(key, 0.0)) + float(value)
        return bucket[key]

    async def hset(self, name, *args, mapping=None):
        bucket = self.hashes[name]
        if mapping is not None:
            for key, value in mapping.items():
                bucket[key] = value
            return len(mapping)
        if len(args) == 2:
            field, value = args
            bucket[field] = value
            return 1
        raise TypeError('Unsupported hset call')

    async def hget(self, name, field):
        return self.hashes.get(name, {}).get(field)

    async def hgetall(self, name):
        bucket = self.hashes.get(name, {})
        return {
            key: (str(value) if isinstance(value, (int, float)) else value)
            for key, value in bucket.items()
        }

    async def hdel(self, name, *fields):
        bucket = self.hashes.get(name, {})
        deleted = 0
        for field in fields:
            if field in bucket:
                del bucket[field]
                deleted += 1
        return deleted

    async def set(self, name, value):
        self.strings[name] = value
        return True

    async def get(self, name):
        return self.strings.get(name)

    async def expire(self, name, seconds):
        self.expirations[name] = int(seconds)
        return 1

    async def keys(self, pattern):
        all_keys = set(self.hashes.keys()) | set(self.strings.keys()) | set(self.hll.keys())
        return [key for key in all_keys if fnmatch(key, pattern)]

    async def delete(self, *names):
        deleted = 0
        for name in names:
            if name in self.hashes:
                deleted += 1
            if name in self.strings:
                deleted += 1
            if name in self.hll:
                deleted += 1
            self.hashes.pop(name, None)
            self.strings.pop(name, None)
            self.hll.pop(name, None)
            self.expirations.pop(name, None)
        return deleted

    async def pfadd(self, name, *values):
        self.hll[name].update(str(v) for v in values)
        return 1

    async def pfcount(self, *names):
        combined = set()
        for name in names:
            combined.update(self.hll.get(name, set()))
        return len(combined)


class FakeDB:
    def __init__(self, redis=None, *, lazy=False):
        self.redis = redis if redis is not None else (None if lazy else FakeRedis())

    async def get_redis(self):
        if self.redis is None:
            self.redis = FakeRedis()
        return self.redis


class FakePoolCache:
    def __init__(self, price_holder):
        self._price_holder = price_holder

    async def get(self):
        return self._price_holder


def make_price_holder(*, include_rune: bool = False) -> PriceHolder:
    ph = PriceHolder(stable_coins=['THOR.RUNE'])
    ph.usd_per_rune = 2.0
    ph.pool_info_map = {
        'BTC.BTC': PoolInfo(
            'BTC.BTC',
            balance_asset=100_000_000,
            balance_rune=1_500_000_000_000,
            pool_units=1,
            status=PoolInfo.AVAILABLE,
            usd_per_asset=30_000.0,
        ),
        'ETH.ETH': PoolInfo(
            'ETH.ETH',
            balance_asset=1_000_000_000,
            balance_rune=1_000_000_000_000,
            pool_units=1,
            status=PoolInfo.AVAILABLE,
            usd_per_asset=2_000.0,
        ),
    }

    if include_rune:
        ph.pool_info_map['THOR.RUNE'] = PoolInfo(
            'THOR.RUNE',
            balance_asset=1,
            balance_rune=1,
            pool_units=1,
            status=PoolInfo.AVAILABLE,
            usd_per_asset=2.0,
        )

    return ph


