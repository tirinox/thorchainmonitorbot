from dataclasses import dataclass, field
from statistics import median

from services.lib.db import DB
from services.lib.utils import linear_transform
from services.models.base import BaseModelMixin
from services.models.time_series import TimeSeries


@dataclass
class LiquidityPoolStats(BaseModelMixin):
    pool: str
    last_tx: str = ''
    usd_depth: float = 0.0
    tx_acc: list = field(default_factory=list)

    KEY_PREFIX = 'liq-pool-stats-v2'
    KEY_POOL_DEPTH = 'POOL-DEPTH'

    @property
    def key(self):
        return f"{self.KEY_PREFIX}:{self.pool}"

    async def save(self, db: DB):
        await db.get_redis()
        await db.redis.set(self.key, self.as_json_string)

    @classmethod
    async def get_from_db(cls, pool, db: DB):
        r = await db.get_redis()
        empty = cls(pool, '', 1, [])
        old_j = await r.get(empty.key)
        return cls.from_json(old_j) if old_j else empty

    def update(self, rune_amount, max_n=50):
        self.tx_acc.append({
            'rune_amount': rune_amount
        })
        n = len(self.tx_acc)
        if n > max_n:
            self.tx_acc = self.tx_acc[(n - max_n):]

    @property
    def n_elements(self):
        return len(self.tx_acc)

    @property
    def median_rune_amount(self):
        return median(tx['rune_amount'] for tx in self.tx_acc) if self.tx_acc else 0.0

    @classmethod
    async def clear_all_data(cls, db: DB):
        r = await db.get_redis()
        keys = await r.keys(f'{cls.KEY_PREFIX}:*')
        if keys:
            await r.delete(*keys)

    @property
    def stream_name(self):
        return f'{self.KEY_POOL_DEPTH}-{self.pool}'

    async def write_time_series(self, db: DB):
        ts = TimeSeries(self.stream_name, db)
        await ts.add(usd_depth=self.usd_depth)

    TX_VS_DEPTH_CURVE = [
        (10_000, 0.2),  # if depth < 10_000 then 0.2
        (100_000, 0.12),  # if 10_000 <= depth < 100_000 then 0.2 ... 0.12
        (500_000, 0.08),  # if 100_000 <= depth < 500_000 then 0.12 ... 0.08
        (1_000_000, 0.05),  # and so on...
        (10_000_000, 0.015),
    ]

    @classmethod
    def curve_for_tx_threshold(cls, depth):
        lower_bound = 0
        lower_percent = cls.TX_VS_DEPTH_CURVE[0][1]
        for upper_bound, upper_percent in cls.TX_VS_DEPTH_CURVE:
            if depth < upper_bound:
                return linear_transform(depth, lower_bound, upper_bound, lower_percent, upper_percent)
            lower_percent = upper_percent
            lower_bound = upper_bound
        return cls.TX_VS_DEPTH_CURVE[-1][1]