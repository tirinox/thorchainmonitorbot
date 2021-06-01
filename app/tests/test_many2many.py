import asyncio

import pytest

from services.lib.db import DB
from services.lib.db_many2many import ManyToManySet


@pytest.fixture(scope="function")
def many2many():
    loop = asyncio.get_event_loop()
    db = DB(loop)
    return ManyToManySet(db, 'Users', 'Groups')


@pytest.mark.asyncio
async def test_clear(many2many: ManyToManySet):
    await many2many.clear()
    assert not await many2many.all_rights('A')
    assert not await many2many.all_rights('B')
    assert not await many2many.all_rights('C')
    assert not await many2many.all_lefts('G1')
    assert not await many2many.all_lefts('G2')
    assert not await many2many.all_lefts('G3')


@pytest.mark.asyncio
async def test_add1(many2many: ManyToManySet):
    await many2many.associate('A', 'G1')
    assert await many2many.all_rights('A') == {'G1'}
    assert await many2many.all_lefts('G1') == {'A'}

    await many2many.associate_many(['B'], ['G1', 'G2'])
    assert await many2many.all_rights('A') == {'G1'}
    assert await many2many.all_rights('B') == {'G1', 'G2'}
    assert await many2many.all_lefts('G1') == {'A', 'B'}

    await many2many.associate_many(['C'], ['G3', 'G2'])
    assert await many2many.all_lefts('G1') == {'A', 'B'}
    assert await many2many.all_lefts('G2') == {'C', 'B'}
    assert await many2many.all_lefts('G3') == {'C'}
    assert await many2many.all_rights('A') == {'G1'}
    assert await many2many.all_rights('B') == {'G1', 'G2'}
    assert await many2many.all_rights('C') == {'G3', 'G2'}

    # don't confuse lefts and rights
    assert not await many2many.all_rights('G1')
    assert not await many2many.all_rights('G2')
    assert not await many2many.all_rights('G3')

    # don't confuse lefts and rights
    assert not await many2many.all_lefts('A')
    assert not await many2many.all_lefts('B')
    assert not await many2many.all_lefts('C')


@pytest.mark.asyncio
async def test_remove(many2many: ManyToManySet):
    await many2many.remove_all_rights('C')

    assert await many2many.all_rights('A') == {'G1'}
    assert await many2many.all_rights('B') == {'G1', 'G2'}
    assert await many2many.all_rights('C') == set()

    await many2many.remove_all_lefts('G1')

    assert await many2many.all_rights('A') == set()
    assert await many2many.all_rights('B') == {'G2'}
    assert await many2many.all_rights('C') == set()

    assert not await many2many.all_rights('G3')
    assert not await many2many.all_rights('G1')
