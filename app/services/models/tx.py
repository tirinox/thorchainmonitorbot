from dataclasses import dataclass, field
from statistics import median

from services.lib.db import DB
from services.models.pool_info import MIDGARD_MULT
from services.models.cap_info import BaseModelMixin
from services.models.time_series import TimeSeries


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
    full_usd: float
    asset_per_rune: float

    KEY_PREFIX = 'tx_not'

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
                   asset_per_rune=0.0,
                   full_usd=0.0)

    def asymmetry(self, force_abs=False):
        rune_asset_amount = self.asset_amount * self.asset_per_rune
        factor = (self.rune_amount / (rune_asset_amount + self.rune_amount) - 0.5) * 200.0  # -100 % ... + 100 %
        return abs(factor) if force_abs else factor

    def symmetry_rune_vs_asset(self):
        f = 100.0 / self.full_rune
        return self.rune_amount * f, self.asset_amount / self.asset_per_rune * f

    @classmethod
    def collect_pools(cls, txs):
        return set(t.pool for t in txs)

    def calc_full_rune_amount(self, asset_per_rune):
        self.asset_per_rune = asset_per_rune
        self.full_rune = self.asset_amount / asset_per_rune + self.rune_amount
        return self.full_rune

    @property
    def notify_key(self):
        return f"{self.KEY_PREFIX}:{self.hash}"

    @classmethod
    async def clear_all_data(cls, db: DB):
        r = await db.get_redis()
        keys = await r.keys(f'{cls.KEY_PREFIX}:*')
        if keys:
            await r.delete(*keys)

    async def is_notified(self, db: DB):
        r = await db.get_redis()
        return bool(await r.get(self.notify_key))

    async def set_notified(self, db: DB, value=1):
        r = await db.get_redis()
        await r.set(self.notify_key, value)


def short_asset_name(pool: str):
    try:
        cs = pool.split('.')
        return cs[1].split('-')[0]
    except IndexError:
        return pool


@dataclass
class StakePoolStats(BaseModelMixin):
    pool: str
    last_tx: str = ''
    usd_depth: float = 0.0
    tx_acc: list = field(default_factory=list)

    KEY_PREFIX = 'stake-pool-stats-v2'
    KEY_POOL_DEPTH = 'POOL-DEPTH'

    @property
    def key(self):
        return f"{self.KEY_PREFIX}:{self.pool}"

    async def save(self, db: DB):
        await db.get_redis()
        await db.redis.set(self.key, self.as_json)

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


def asset_name_cut_chain(asset):
    try:
        cs = asset.split('.')
        return cs[1]
    except IndexError:
        return asset
