import asyncio

import pytest

from lib.db import DB
from lib.db_one2one import OneToOne


@pytest.fixture(scope="function")
def one2one():
    loop = asyncio.get_event_loop()
    db = DB(loop)
    return OneToOne(db, 'Test')


@pytest.mark.asyncio
async def test_simple(one2one: OneToOne):
    await one2one.clear()
    await one2one.put('1', '2')
    assert await one2one.get('1') == '2'
    assert await one2one.get('2') == '1'
    assert await one2one.get(1) == '2'
    assert await one2one.get(2) == '1'

    assert not await one2one.get('3')
    assert not await one2one.get(None)

    await one2one.delete('1')
    assert not await one2one.get('1')
    assert not await one2one.get('2')


@pytest.mark.asyncio
async def test_same_name(one2one: OneToOne):
    await one2one.clear()
    await one2one.put('foo', 'foo')
    assert await one2one.get('foo') == 'foo'
    await one2one.delete('foo')
    assert await one2one.get('foo') is None


@pytest.mark.asyncio
async def test_clear(one2one: OneToOne):
    await one2one.clear()
    await one2one.put('1', '2')
    await one2one.put('3', '4')
    await one2one.put('5', '6')
    assert await one2one.get('6') == '5'

    await one2one.clear()
    assert not await one2one.get('1')
    assert not await one2one.get('2')
    assert not await one2one.get('3')
    assert not await one2one.get('4')
    assert not await one2one.get('5')
    assert not await one2one.get('6')


@pytest.mark.asyncio
async def test_confuse(one2one: OneToOne):
    await one2one.clear()
    await one2one.put('me', 'good')
    await one2one.put('good', 'evil')

    assert not await one2one.get('me')
    assert await one2one.get('good') == 'evil'
    assert await one2one.get('evil') == 'good'

    await one2one.clear()
    await one2one.put('me', '123')
    await one2one.put('me', '345')

    assert not await one2one.get('123')
    assert await one2one.get('me') == '345'
    assert await one2one.get('345') == 'me'
