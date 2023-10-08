import asyncio

import pytest

from services.lib.db import DB
from services.lib.db_many2many import ManyToManySet


@pytest.fixture(scope='session')
async def many2many_example():
    loop = asyncio.get_event_loop()
    db = DB(loop)

    many2many = ManyToManySet(db, 'left', 'right')

    await many2many.clear()
    await many2many.associate('A', 'G1')
    await many2many.associate_many(['B'], ['G1', 'G2'])
    await many2many.associate_many(['C'], ['G3', 'G2'])

    return many2many


@pytest.mark.asyncio
async def test_has(many2many_example):
    mm = await many2many_example

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
    mm = await many2many_example
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
    mm = await many2many_example

    await mm.clear()

    assert not await mm.all_rights_for_left_one('A')
    assert not await mm.all_rights_for_left_one('B')
    assert not await mm.all_rights_for_left_one('C')
    assert not await mm.all_lefts_for_right_one('G1')
    assert not await mm.all_lefts_for_right_one('G2')
    assert not await mm.all_lefts_for_right_one('G3')


@pytest.mark.asyncio
async def test_add1(many2many_example):
    mm = await many2many_example

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
    mm = await many2many_example

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
    mm = await many2many_example

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
    mm = await many2many_example

    assert await mm.all_lefts() == {'A', 'B', 'C'}
    assert await mm.all_rights() == {'G1', 'G2', 'G3'}

    await mm.remove_all_lefts('G3')
    await mm.remove_all_lefts('G2')

    assert await mm.all_lefts() == {'A', 'B'}
