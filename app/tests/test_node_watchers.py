import asyncio

import pytest

from lib.db import DB
from lib.depcont import DepContainer
from lib.utils import parse_list_from_string
from models.node_watchers import NodeWatcherStorage


@pytest.fixture(scope="function")
def deps():
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.db = DB()
    return d


@pytest.fixture(scope="function")
def node_watcher(deps: DepContainer):
    return NodeWatcherStorage(deps.db)


@pytest.mark.asyncio
async def test_names(node_watcher: NodeWatcherStorage):
    nns = node_watcher.node_name_storage
    await nns.set_node_name('11', 'thorA', 'Apricot')
    await nns.set_node_name('11', 'thorB', 'Banana')
    await nns.set_node_name('11', 'thorC', 'Cucumber')

    await nns.set_node_name('88', 'thorA', 'Astoria')
    await nns.set_node_name('88', 'thorB', 'Brownie')
    await nns.set_node_name('88', 'thorC', 'Cafe')

    names1 = await nns(['thorA', 'thorB', 'thorC'])
    assert names1 == {'thorA': 'Apricot', 'thorB': 'Banana', 'thorC': 'Cucumber'}

    names11 = await nns.get_node_names(['thorD', 'thorA'])
    assert names11 == {'thorA': 'Apricot', 'thorD': None}

    # test: are keys overlap?
    names2 = await nns.get_node_names(['thorA', 'thorB', 'thorC'])
    assert names2 == {'thorA': 'Astoria', 'thorB': 'Brownie', 'thorC': 'Cafe'}

    # test: remove name
    await nns('88', 'thorA', None)
    names1 = await nns.get_node_names(['thorA', 'thorB', 'thorC'])
    assert names1 == {'thorA': None, 'thorB': 'Banana', 'thorC': 'Cucumber'}

    # test update names
    await nns.set_node_name('11', 'thorA', 'Apple')
    await nns.set_node_name('11', 'thorB', 'Burger')
    names1 = await nns.get_node_names(['thorA', 'thorB'])
    assert names1 == {'thorA': 'Apple', 'thorB': 'Burger'}


def test_multi_split():
    assert parse_list_from_string("") == []
    assert parse_list_from_string("\n") == []
    assert parse_list_from_string("\t") == []
    assert parse_list_from_string(",") == []
    assert parse_list_from_string("    ") == []
    assert parse_list_from_string(", , ; ; \n \t \n ; ,") == []
    assert parse_list_from_string("    ; ;    \n") == []
    assert parse_list_from_string("test") == ['test']
    assert parse_list_from_string("TeSt", lower=True) == ['test']
    assert parse_list_from_string(";TeSt,", upper=True) == ['TEST']
    assert parse_list_from_string("TeSt;fOo", upper=True) == ['TEST', 'FOO']

    assert parse_list_from_string("xqmm") == ["xqmm"]

    assert parse_list_from_string("thorA, THORB, tHorC", upper=True) == ['THORA', 'THORB', 'THORC']
    assert parse_list_from_string("thorA  , THORB    ; tHorC", upper=True) == ['THORA', 'THORB', 'THORC']
    assert parse_list_from_string("thorA  , THORB    ; tHorC", upper=True) == ['THORA', 'THORB', 'THORC']
    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC", upper=True) == ['THORA', 'THORB', 'THORC']

    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC") == ['thorA', 'THORB', 'tHorC']

    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC") == ['thorA', 'THORB', 'tHorC']
    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC") == ['thorA', 'THORB', 'tHorC']

    assert parse_list_from_string("""
      thora,
      ThorB
      thorc;foo
    """, upper=True) == ['THORA', 'THORB', 'THORC', 'FOO']
