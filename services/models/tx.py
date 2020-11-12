from dataclasses import dataclass

from services.db import DB
from services.models.pool_info import MIDGARD_MULT
from services.models.cap_info import BaseModelMixin


@dataclass
class StakeTx(BaseModelMixin):
    date: int
    type: str
    pool: str
    address: str
    asset_amount: float
    rune_amount: float
    hash: str
    full_rune: float
    asset_price: float

    @classmethod
    def load_from_midgard(cls, j):
        t = j['type']
        pool = j['pool']

        if t == 'stake':
            coins = j['in']['coins']
            if coins[0]['asset'] == pool:
                asset_amount = float(coins[0]['amount'])
                rune_amount = float(coins[1]['amount']) if len(coins) >= 2 else 0.0
            else:
                asset_amount = float(coins[1]['amount']) if len(coins) >= 2 else 0.0
                rune_amount = float(coins[0]['amount'])
        elif t == 'unstake':
            out = j['out']
            if out[0]['coins'][0]['asset'] == pool:
                asset_amount = float(out[0]['coins'][0]['amount'])
                rune_amount = float(out[1]['coins'][0]['amount'])
            else:
                asset_amount = float(out[1]['coins'][0]['amount'])
                rune_amount = float(out[0]['coins'][0]['amount'])
        else:
            return None

        tx_hash = j['in']['txID']
        address = j['in']['address']

        return cls(date=int(j['date']),
                   type=t,
                   pool=pool,
                   address=address,
                   asset_amount=asset_amount * MIDGARD_MULT,
                   rune_amount=rune_amount * MIDGARD_MULT,
                   hash=tx_hash,
                   full_rune=0.0,
                   asset_price=0.0)

    def asymmetry(self, force_abs=False):
        rune_asset_amount = self.asset_amount * self.asset_price
        factor = (self.rune_amount / (rune_asset_amount + self.rune_amount) - 0.5) * 200.0  # -100 % ... + 100 %
        return abs(factor) if force_abs else factor

    def symmetry_rune_vs_asset(self):
        f = 100.0 / self.full_rune
        return self.rune_amount * f, self.asset_price * self.asset_amount * f

    @classmethod
    def collect_pools(cls, txs):
        return set(t.pool for t in txs)

    def full_rune_amount(self, asset_price):
        self.asset_price = asset_price
        self.full_rune = self.asset_amount / asset_price + self.rune_amount
        return self.full_rune

    @property
    def notify_key(self):
        return f"tx_not:{self.hash}"

    async def is_notified(self, db: DB):
        r = await db.get_redis()
        return bool(await r.get(self.notify_key))

    async def set_notified(self, db: DB, value=1):
        r = await db.get_redis()
        await r.set(self.notify_key, value)


@dataclass
class StakePoolStats(BaseModelMixin):
    pool: str
    last_tx: str
    rune_avg_amt: float
    n_tracked: int

    START_RUNE_AMT = 5000

    @property
    def key(self):
        return f"stake_pool_stats:{self.pool}"

    async def save(self, db: DB):
        await db.redis.set(self.key, self.as_json)

    @classmethod
    async def get_from_db(cls, pool, db: DB):
        empty = cls(pool, '', cls.START_RUNE_AMT, 1)
        old_j = await db.redis.get(empty.key)
        return cls.from_json(old_j) if old_j else empty

    def update(self, rune_amount, avg_n=10):
        self.rune_avg_amt -= self.rune_avg_amt / self.n_tracked
        self.rune_avg_amt += rune_amount / self.n_tracked
        self.n_tracked = min(self.n_tracked + 1, avg_n)
        return self.rune_avg_amt

    @classmethod
    async def clear_all_data(cls, db: DB):
        r = await db.get_redis()
        keys = await r.keys('stake_pool_stats:*')
        keys += await r.keys('tx_not:*')
        if keys:
            await r.delete(*keys)


def short_asset_name(pool: str):
    try:
        cs = pool.split('.')
        return cs[1].split('-')[0]
    except IndexError:
        return pool
