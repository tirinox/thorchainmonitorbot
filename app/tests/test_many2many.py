from collections import defaultdict
from fnmatch import fnmatch

import pytest

from lib.db_many2many import ManyToManySet


class MemoryPipeline:
    def __init__(self, redis, transaction):
        self.redis = redis
        self.transaction = transaction
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    def smembers(self, name):
        self.commands.append(name)
        return self

    async def execute(self):
        self.redis.pipeline_executions += 1
        self.redis.last_pipeline_transaction = self.transaction
        self.redis.last_pipeline_size = len(self.commands)
        return [set(self.redis.sets[name]) for name in self.commands]


class MemoryRedis:
    def __init__(self):
        self.sets = defaultdict(set)
        self.pipeline_executions = 0
        self.last_pipeline_transaction = None
        self.last_pipeline_size = 0
        self.direct_smembers_calls = 0

    def pipeline(self, transaction=True):
        return MemoryPipeline(self, transaction)

    async def keys(self, pattern):
        return [key for key in self.sets if fnmatch(key, pattern)]

    async def delete(self, *keys):
        for key in keys:
            self.sets.pop(key, None)

    async def sadd(self, key, *values):
        self.sets[key].update(values)

    async def smembers(self, key):
        self.direct_smembers_calls += 1
        return set(self.sets[key])

    async def sismember(self, key, value):
        return value in self.sets[key]

    async def srem(self, key, *values):
        self.sets[key].difference_update(values)
        if not self.sets[key]:
            del self.sets[key]


class MemoryDB:
    def __init__(self):
        self.redis = MemoryRedis()

    async def get_redis(self):
        return self.redis


@pytest.fixture
def many2many_example():
    db = MemoryDB()
    many2many = ManyToManySet(db, 'left', 'right')
    db.redis.sets[many2many.left_key('A')].add('G1')
    db.redis.sets[many2many.left_key('B')].update(['G1', 'G2'])
    db.redis.sets[many2many.left_key('C')].update(['G2', 'G3'])
    db.redis.sets[many2many.right_key('G1')].update(['A', 'B'])
    db.redis.sets[many2many.right_key('G2')].update(['B', 'C'])
    db.redis.sets[many2many.right_key('G3')].add('C')
    return many2many


@pytest.mark.asyncio
async def test_get_many_uses_one_pipeline_for_large_batch():
    db = MemoryDB()
    mm = ManyToManySet(db, 'left', 'right')
    rights = [f'G{i}' for i in range(178)]
    for index, right in enumerate(rights):
        db.redis.sets[mm.right_key(right)].add(f'U{index}')

    result = await mm.all_lefts_for_many_rights(rights, flatten=False)

    assert result == {right: {f'U{index}'} for index, right in enumerate(rights)}
    assert db.redis.pipeline_executions == 1
    assert db.redis.last_pipeline_transaction is False
    assert db.redis.last_pipeline_size == 178
    assert db.redis.direct_smembers_calls == 0


@pytest.mark.asyncio
async def test_has(many2many_example):
    mm = many2many_example

    assert await mm.has_left('A', 'G1')
    assert await mm.has_left('B', 'G1')
    assert await mm.has_left('C', 'G3')

    assert not await mm.has_left('C', 'G1')
    assert not await mm.has_left('C', '')
    assert not await mm.has_left('', 'G1')
    assert not await mm.has_left('G1', 'A')
    assert not await mm.has_left('G2', 'B')

    assert await mm.has_right('A', 'G1')
    assert await mm.has_right('B', 'G1')
    assert await mm.has_right('C', 'G3')

    assert not await mm.has_right('C', 'G1')
    assert not await mm.has_right('C', '')
    assert not await mm.has_right('', 'G1')
    assert not await mm.has_right('G1', 'A')
    assert not await mm.has_right('G2', 'B')


@pytest.mark.asyncio
async def test_get_many_from_many(many2many_example):
    mm = many2many_example
    assert await mm.all_lefts_for_many_rights(['G1', 'G3', 'G2']) == {'A', 'B', 'C'}
    assert await mm.all_lefts_for_many_rights(['G1']) == {'A', 'B'}
    assert await mm.all_lefts_for_many_rights(['G3', 'G2']) == {'C', 'B'}
    assert await mm.all_lefts_for_many_rights([]) == set()

    assert await mm.all_rights_for_many_lefts(['A']) == {'G1'}
    assert await mm.all_rights_for_many_lefts(['A', 'C']) == {'G1', 'G2', 'G3'}
    assert await mm.all_rights_for_many_lefts(['B', 'C']) == {'G1', 'G2', 'G3'}
    assert await mm.all_rights_for_many_lefts([]) == set()

    assert await mm.all_rights_for_many_lefts(['A'], flatten=False) == {'A': {'G1'}}
    assert await mm.all_rights_for_many_lefts(['A', 'C'], flatten=False) == {'A': {'G1'}, 'C': {'G2', 'G3'}}
    assert await mm.all_rights_for_many_lefts(['B', 'C'], flatten=False) == {'B': {'G1', 'G2'},
                                                                             'C': {'G2', 'G3'}}


@pytest.mark.asyncio
async def test_clear(many2many_example):
    mm = many2many_example

    await mm.clear()

    assert not await mm.all_rights_for_left_one('A')
    assert not await mm.all_rights_for_left_one('B')
    assert not await mm.all_rights_for_left_one('C')
    assert not await mm.all_lefts_for_right_one('G1')
    assert not await mm.all_lefts_for_right_one('G2')
    assert not await mm.all_lefts_for_right_one('G3')


@pytest.mark.asyncio
async def test_add1(many2many_example):
    mm = many2many_example

    await mm.clear()

    await mm.associate('A', 'G1')
    assert await mm.all_rights_for_left_one('A') == {'G1'}
    assert await mm.all_lefts_for_right_one('G1') == {'A'}

    await mm.associate_many(['B'], ['G1', 'G2'])
    assert await mm.all_rights_for_left_one('A') == {'G1'}
    assert await mm.all_rights_for_left_one('B') == {'G1', 'G2'}
    assert await mm.all_lefts_for_right_one('G1') == {'A', 'B'}

    await mm.associate_many(['C'], ['G3', 'G2'])
    assert await mm.all_lefts_for_right_one('G1') == {'A', 'B'}
    assert await mm.all_lefts_for_right_one('G2') == {'C', 'B'}
    assert await mm.all_lefts_for_right_one('G3') == {'C'}
    assert await mm.all_rights_for_left_one('A') == {'G1'}
    assert await mm.all_rights_for_left_one('B') == {'G1', 'G2'}
    assert await mm.all_rights_for_left_one('C') == {'G3', 'G2'}

    # don't confuse lefts and rights
    assert not await mm.all_rights_for_left_one('G1')
    assert not await mm.all_rights_for_left_one('G2')
    assert not await mm.all_rights_for_left_one('G3')

    # don't confuse lefts and rights
    assert not await mm.all_lefts_for_right_one('A')
    assert not await mm.all_lefts_for_right_one('B')
    assert not await mm.all_lefts_for_right_one('C')


@pytest.mark.asyncio
async def test_remove_side(many2many_example):
    mm = many2many_example

    await mm.remove_all_rights('C')

    assert await mm.all_rights_for_left_one('A') == {'G1'}
    assert await mm.all_rights_for_left_one('B') == {'G1', 'G2'}
    assert await mm.all_rights_for_left_one('C') == set()

    await mm.remove_all_lefts('G1')

    assert await mm.all_rights_for_left_one('A') == set()
    assert await mm.all_rights_for_left_one('B') == {'G2'}
    assert await mm.all_rights_for_left_one('C') == set()

    assert not await mm.all_rights_for_left_one('G3')
    assert not await mm.all_rights_for_left_one('G1')


@pytest.mark.asyncio
async def test_remove_1(many2many_example):
    mm = many2many_example

    await mm.associate('A', 'G1')
    await mm.associate_many(['B'], ['G1', 'G2'])
    await mm.associate_many(['C', 'D'], ['G3', 'G2'])

    await mm.remove_one_item('D', 'G2')

    assert await mm.all_rights_for_left_one('D') == {'G3'}
    assert await mm.all_rights_for_left_one('C') == {'G3', 'G2'}

    await mm.remove_one_item('D', 'G3')

    assert await mm.all_rights_for_left_one('D') == set()
    assert await mm.all_rights_for_left_one('C') == {'G3', 'G2'}
    assert await mm.all_lefts_for_right_one('G3') == {'C'}

    await mm.associate('D', 'G4')
    assert await mm.all_rights_for_left_one('D') == {'G4'}
    assert await mm.all_lefts_for_right_one('G4') == {'D'}

    await mm.remove_one_item('D', 'G4')

    assert await mm.all_rights_for_left_one('D') == set()
    assert await mm.all_lefts_for_right_one('G4') == set()


@pytest.mark.asyncio
async def test_all_one_side(many2many_example):
    mm = many2many_example

    assert await mm.all_lefts() == {'A', 'B', 'C'}
    assert await mm.all_rights() == {'G1', 'G2', 'G3'}

    await mm.remove_all_lefts('G3')
    await mm.remove_all_lefts('G2')

    assert await mm.all_lefts() == {'A', 'B'}
