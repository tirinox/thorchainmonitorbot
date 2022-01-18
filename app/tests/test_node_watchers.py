import asyncio

import pytest

from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.utils import parse_list_from_string
from services.models.node_watchers import NodeWatcherStorage


@pytest.fixture(scope="function")
def deps():
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.db = DB(d.loop)
    return d


@pytest.fixture(scope="function")
def node_watcher(deps: DepContainer):
    return NodeWatcherStorage(deps.db, '8888')


@pytest.mark.asyncio
async def test_names(node_watcher: NodeWatcherStorage):
    await node_watcher.set_node_name('thorA', 'Apricot')
    await node_watcher.set_node_name('thorB', 'Banana')
    await node_watcher.set_node_name('thorC', 'Cucumber')

    node_watcher2 = NodeWatcherStorage(node_watcher.db, '111111')
    await node_watcher2.set_node_name('thorA', 'Astoria')
    await node_watcher2.set_node_name('thorB', 'Brownie')
    await node_watcher2.set_node_name('thorC', 'Cafe')

    names1 = await node_watcher.get_node_names(['thorA', 'thorB', 'thorC'])
    assert names1 == {'thorA': 'Apricot', 'thorB': 'Banana', 'thorC': 'Cucumber'}

    names11 = await node_watcher.get_node_names(['thorD', 'thorA'])
    assert names11 == {'thorA': 'Apricot', 'thorD': None}

    # test: are keys overlap?
    names2 = await node_watcher2.get_node_names(['thorA', 'thorB', 'thorC'])
    assert names2 == {'thorA': 'Astoria', 'thorB': 'Brownie', 'thorC': 'Cafe'}

    # test: remove name
    await node_watcher.set_node_name('thorA', None)
    names1 = await node_watcher.get_node_names(['thorA', 'thorB', 'thorC'])
    assert names1 == {'thorA': None, 'thorB': 'Banana', 'thorC': 'Cucumber'}

    # test update names
    await node_watcher.set_node_name('thorA', 'Apple')
    await node_watcher.set_node_name('thorB', 'Burger')
    names1 = await node_watcher.get_node_names(['thorA', 'thorB'])
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
