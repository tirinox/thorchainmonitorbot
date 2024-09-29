import asyncio

import pytest

from comm.dialog.message_cat_db import MessageCategoryDB
from lib.db import DB


@pytest.fixture(scope='session')
async def m_cat_db():
    loop = asyncio.get_event_loop()
    db = DB(loop)
    await db.get_redis()

    db = MessageCategoryDB(db, 123, 'test')
    await db.clear()
    return db


@pytest.mark.asyncio
async def test_push_pop(m_cat_db):
    m_cat_db = await m_cat_db
    await m_cat_db.push(10000001)
    await m_cat_db.push(10000002)
    await m_cat_db.push(10000003)
    await m_cat_db.push(10000005)
    await m_cat_db.push(10000002)
    await m_cat_db.push(10000010, 10000011, 10000011)
    s_all = {'10000001', '10000002', '10000003', '10000005', '10000010', '10000011'}
    assert await m_cat_db.get_all() == s_all

    r = await m_cat_db.pop()
    assert r in s_all

    message_id = await m_cat_db.pop()
    while message_id:
        message_id = await m_cat_db.pop()

    assert await m_cat_db.get_all() == set()
