import asyncio

import pytest

from services.lib.db import DB
from services.lib.db_many2many import ManyToManySet


@pytest.fixture(scope="function")
def many2many():
    loop = asyncio.get_event_loop()
    db = DB(loop)
    return ManyToManySet(db, 'Users', 'Groups')


async def prepare_simple(many2many):
    await many2many.clear()
    await many2many.associate('A', 'G1')
    await many2many.associate_many(['B'], ['G1', 'G2'])
    await many2many.associate_many(['C'], ['G3', 'G2'])


@pytest.mark.asyncio
async def test_has(many2many: ManyToManySet):
    assert await many2many.has_left('A', 'G1')
    assert await many2many.has_left('B', 'G1')
    assert await many2many.has_left('C', 'G3')

    assert not await many2many.has_left('C', 'G1')
    assert not await many2many.has_left('C', '')
    assert not await many2many.has_left('', 'G1')
    assert not await many2many.has_left('G1', 'A')
    assert not await many2many.has_left('G2', 'B')

    assert await many2many.has_right('A', 'G1')
    assert await many2many.has_right('B', 'G1')
    assert await many2many.has_right('C', 'G3')

    assert not await many2many.has_right('C', 'G1')
    assert not await many2many.has_right('C', '')
    assert not await many2many.has_right('', 'G1')
    assert not await many2many.has_right('G1', 'A')
    assert not await many2many.has_right('G2', 'B')


@pytest.mark.asyncio
async def test_get_many_from_many(many2many: ManyToManySet):
    await prepare_simple(many2many)
    assert await many2many.all_lefts_for_many_rights(['G1', 'G3', 'G2']) == {'A', 'B', 'C'}
    assert await many2many.all_lefts_for_many_rights(['G1']) == {'A', 'B'}
    assert await many2many.all_lefts_for_many_rights(['G3', 'G2']) == {'C', 'B'}
    assert await many2many.all_lefts_for_many_rights([]) == set()

    assert await many2many.all_rights_for_many_lefts(['A']) == {'G1'}
    assert await many2many.all_rights_for_many_lefts(['A', 'C']) == {'G1', 'G2', 'G3'}
    assert await many2many.all_rights_for_many_lefts(['B', 'C']) == {'G1', 'G2', 'G3'}
    assert await many2many.all_rights_for_many_lefts([]) == set()

    assert await many2many.all_rights_for_many_lefts(['A'], flatten=False) == {'A': {'G1'}}
    assert await many2many.all_rights_for_many_lefts(['A', 'C'], flatten=False) == {'A': {'G1'}, 'C': {'G2', 'G3'}}
    assert await many2many.all_rights_for_many_lefts(['B', 'C'], flatten=False) == {'B': {'G1', 'G2'},
                                                                                    'C': {'G2', 'G3'}}


@pytest.mark.asyncio
async def test_clear(many2many: ManyToManySet):
    await prepare_simple(many2many)

    await many2many.clear()

    assert not await many2many.all_rights_for_left_one('A')
    assert not await many2many.all_rights_for_left_one('B')
    assert not await many2many.all_rights_for_left_one('C')
    assert not await many2many.all_lefts_for_right_one('G1')
    assert not await many2many.all_lefts_for_right_one('G2')
    assert not await many2many.all_lefts_for_right_one('G3')


@pytest.mark.asyncio
async def test_add1(many2many: ManyToManySet):
    await many2many.associate('A', 'G1')
    assert await many2many.all_rights_for_left_one('A') == {'G1'}
    assert await many2many.all_lefts_for_right_one('G1') == {'A'}

    await many2many.associate_many(['B'], ['G1', 'G2'])
    assert await many2many.all_rights_for_left_one('A') == {'G1'}
    assert await many2many.all_rights_for_left_one('B') == {'G1', 'G2'}
    assert await many2many.all_lefts_for_right_one('G1') == {'A', 'B'}

    await many2many.associate_many(['C'], ['G3', 'G2'])
    assert await many2many.all_lefts_for_right_one('G1') == {'A', 'B'}
    assert await many2many.all_lefts_for_right_one('G2') == {'C', 'B'}
    assert await many2many.all_lefts_for_right_one('G3') == {'C'}
    assert await many2many.all_rights_for_left_one('A') == {'G1'}
    assert await many2many.all_rights_for_left_one('B') == {'G1', 'G2'}
    assert await many2many.all_rights_for_left_one('C') == {'G3', 'G2'}

    # don't confuse lefts and rights
    assert not await many2many.all_rights_for_left_one('G1')
    assert not await many2many.all_rights_for_left_one('G2')
    assert not await many2many.all_rights_for_left_one('G3')

    # don't confuse lefts and rights
    assert not await many2many.all_lefts_for_right_one('A')
    assert not await many2many.all_lefts_for_right_one('B')
    assert not await many2many.all_lefts_for_right_one('C')


@pytest.mark.asyncio
async def test_remove_side(many2many: ManyToManySet):
    await many2many.remove_all_rights('C')

    assert await many2many.all_rights_for_left_one('A') == {'G1'}
    assert await many2many.all_rights_for_left_one('B') == {'G1', 'G2'}
    assert await many2many.all_rights_for_left_one('C') == set()

    await many2many.remove_all_lefts('G1')

    assert await many2many.all_rights_for_left_one('A') == set()
    assert await many2many.all_rights_for_left_one('B') == {'G2'}
    assert await many2many.all_rights_for_left_one('C') == set()

    assert not await many2many.all_rights_for_left_one('G3')
    assert not await many2many.all_rights_for_left_one('G1')


@pytest.mark.asyncio
async def test_remove_1(many2many: ManyToManySet):
    await many2many.associate('A', 'G1')
    await many2many.associate_many(['B'], ['G1', 'G2'])
    await many2many.associate_many(['C', 'D'], ['G3', 'G2'])

    await many2many.remove_one_item('D', 'G2')

    assert await many2many.all_rights_for_left_one('D') == {'G3'}
    assert await many2many.all_rights_for_left_one('C') == {'G3', 'G2'}

    await many2many.remove_one_item('D', 'G3')

    assert await many2many.all_rights_for_left_one('D') == set()
    assert await many2many.all_rights_for_left_one('C') == {'G3', 'G2'}
    assert await many2many.all_lefts_for_right_one('G3') == {'C'}

    await many2many.associate('D', 'G4')
    assert await many2many.all_rights_for_left_one('D') == {'G4'}
    assert await many2many.all_lefts_for_right_one('G4') == {'D'}

    await many2many.remove_one_item('D', 'G4')

    assert await many2many.all_rights_for_left_one('D') == set()
    assert await many2many.all_lefts_for_right_one('G4') == set()


@pytest.mark.asyncio
async def test_all_one_side(many2many: ManyToManySet):
    await prepare_simple(many2many)

    assert await many2many.all_lefts() == {'A', 'B', 'C'}
    assert await many2many.all_rights() == {'G1', 'G2', 'G3'}

    await many2many.remove_all_lefts('G3')
    await many2many.remove_all_lefts('G2')

    assert await many2many.all_lefts() == {'A', 'B'}
