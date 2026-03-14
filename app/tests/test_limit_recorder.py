from collections import defaultdict

import pytest

from jobs.limit_recorder import LimitSwapStatsRecorder
from jobs.scanner.limit_detector import LimitSwapBlockUpdate, ClosedLimitSwap
from jobs.scanner.tx import NativeThorTx, ThorEvent, ThorTxMessage
from lib.depcont import DepContainer
from models.pool_info import PoolInfo
from models.price import PriceHolder


class FakeRedis:
    def __init__(self):
        self.hashes = defaultdict(dict)
        self.hll = defaultdict(set)

    async def hincrbyfloat(self, name, key, value):
        bucket = self.hashes[name]
        bucket[key] = float(bucket.get(key, 0.0)) + float(value)
        return bucket[key]

    async def hset(self, name, *args, mapping=None):
        bucket = self.hashes[name]
        if mapping is not None:
            for k, v in mapping.items():
                bucket[k] = v
            return len(mapping)
        if len(args) == 2:
            field, value = args
            bucket[field] = value
            return 1
        raise TypeError("Unsupported hset call")

    async def hget(self, name, field):
        return self.hashes.get(name, {}).get(field)

    async def hgetall(self, name):
        bucket = self.hashes.get(name, {})
        return {
            k: (str(v) if isinstance(v, (int, float)) else v)
            for k, v in bucket.items()
        }

    async def hdel(self, name, *fields):
        bucket = self.hashes.get(name, {})
        deleted = 0
        for field in fields:
            if field in bucket:
                del bucket[field]
                deleted += 1
        return deleted

    async def pfadd(self, name, *values):
        self.hll[name].update(str(v) for v in values)
        return 1

    async def pfcount(self, *names):
        combined = set()
        for name in names:
            combined.update(self.hll.get(name, set()))
        return len(combined)

    async def delete(self, *names):
        for name in names:
            self.hashes.pop(name, None)
            self.hll.pop(name, None)


class FakeDB:
    def __init__(self):
        self.redis = FakeRedis()

    async def get_redis(self):
        return self.redis


class FakeDedup:
    def __init__(self, db, key, *args, **kwargs):
        self.seen = set()
        self.key = key

    async def only_new_hashes(self, hashes):
        return [h for h in hashes if h and h not in self.seen]

    async def mark_as_seen(self, tx_id):
        if tx_id:
            self.seen.add(tx_id)


class FakePoolCache:
    def __init__(self, ph):
        self._ph = ph

    async def get(self):
        return self._ph


def make_price_holder():
    ph = PriceHolder(stable_coins=['THOR.RUNE'])
    ph.usd_per_rune = 2.0
    ph.pool_info_map = {
        'BTC.BTC': PoolInfo('BTC.BTC', balance_asset=100_000_000, balance_rune=1_500_000_000_000,
                            pool_units=1, status=PoolInfo.AVAILABLE, usd_per_asset=30_000.0),
        'ETH.ETH': PoolInfo('ETH.ETH', balance_asset=1_000_000_000, balance_rune=1_000_000_000_000,
                            pool_units=1, status=PoolInfo.AVAILABLE, usd_per_asset=2_000.0),
    }
    return ph


def make_deposit_tx(tx_hash: str, memo: str, asset: str, amount: int, signer: str, height: int, timestamp: int):
    msg = ThorTxMessage.from_dict({
        '@type': ThorTxMessage.MsgDeposit,
        'coins': [{'asset': asset, 'amount': str(amount)}],
        'signer': signer,
    })
    return NativeThorTx(
        tx_hash=tx_hash,
        code=0,
        events=[],
        height=height,
        original={},
        signers=[],
        messages=[msg],
        memo=memo,
        timestamp=timestamp,
    )


def make_event(ev_type: str, **attrs):
    data = {'type': ev_type, **attrs}
    return ThorEvent.from_dict(data, height=int(attrs.get('_height', 0) or 0))


@pytest.mark.asyncio
async def test_limit_recorder_daily_stats(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'TxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = FakeDB()
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    day1 = 1_700_000_000
    day2 = day1 + 86_400

    tx1 = make_deposit_tx(
        tx_hash='open-1',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        asset='BTC.BTC',
        amount=100_000_000,
        signer='thor1alice',
        height=100,
        timestamp=day1,
    )
    tx2 = make_deposit_tx(
        tx_hash='open-2',
        memo='=<:BTC.BTC:thor1dest:100000000/100800/0',
        asset='ETH.ETH',
        amount=100_000_000,
        signer='thor1bob',
        height=101,
        timestamp=day1,
    )

    opened_update = LimitSwapBlockUpdate(
        block_no=101,
        timestamp=day1,
        new_opened_limit_swaps=[tx1, tx2],
        closed_limit_swaps=[],
        partial_swaps=[],
    )

    await recorder.on_data(None, opened_update)
    # Repeat exact same batch; dedup should prevent double counting.
    await recorder.on_data(None, opened_update)

    day1_stats = await recorder.accumulator.get(day1)
    assert day1_stats['opened_count'] == 2.0
    assert day1_stats['opened_usd'] == 32_000.0
    assert day1_stats['unique_traders'] == 2.0
    assert day1_stats['pair:BTC.BTC->ETH.ETH:opened_count'] == 1.0
    assert day1_stats['pair:BTC.BTC->ETH.ETH:opened_usd'] == 30_000.0
    assert day1_stats['pair:ETH.ETH->BTC.BTC:opened_count'] == 1.0
    assert day1_stats['pair:ETH.ETH->BTC.BTC:opened_usd'] == 2_000.0

    partial = make_event(
        'swap',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        id='open-1',
        asset='BTC.BTC',
        amount='50000000',
    )
    close = make_event(
        'limit_swap_close',
        reason='limit swap expired',
        id='open-1',
    )

    close_update = LimitSwapBlockUpdate(
        block_no=110,
        timestamp=day2,
        new_opened_limit_swaps=[],
        closed_limit_swaps=[ClosedLimitSwap(close, 'limit swap expired')],
        partial_swaps=[partial],
    )

    await recorder.on_data(None, close_update)
    # Repeat exact same close/partial batch; dedup should prevent double counting.
    await recorder.on_data(None, close_update)

    day2_stats = await recorder.accumulator.get(day2)
    assert day2_stats['partial_count'] == 1.0
    assert day2_stats['partial_usd'] == 15_000.0
    assert day2_stats['closed_count'] == 1.0
    assert day2_stats['closed_reason:limit_swap_expired'] == 1.0
    assert day2_stats['closed_duration_blocks_sum'] == 10.0
    assert day2_stats['closed_duration_samples'] == 1.0
    assert day2_stats['avg_duration_blocks'] == 10.0

    meta_after_close = await recorder._load_open_meta('open-1')
    assert meta_after_close is None

