import asyncio
import json
from types import SimpleNamespace

import pytest

from web_api import AppSettingsAPI


class FakeThorConnector:
    def __init__(self, responses):
        self.env = SimpleNamespace(path_nodes='/thorchain/nodes')
        self.responses = list(responses)
        self.calls = 0

    async def query_raw(self, path):
        assert path == '/thorchain/nodes'
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _make_api(responses):
    # skip __init__: it needs a config file and Redis
    api = AppSettingsAPI.__new__(AppSettingsAPI)
    api.deps = SimpleNamespace(thor_connector=FakeThorConnector(responses))
    api._nodes = None
    api._nodes_ts = 0.0
    api._nodes_lock = asyncio.Lock()
    return api


def _node(address, bond='100000000'):
    return {
        'node_address': address, 'status': 'Active', 'total_bond': bond, 'version': '3.10.0',
        'ip_address': '1.2.3.4', 'jail': {}, 'observe_chains': [],
    }


async def _get(api):
    resp = await api._get_nodes(None)
    return resp.status_code, json.loads(resp.body)


@pytest.mark.asyncio
async def test_nodes_are_trimmed_and_cached():
    api = _make_api([[_node('thor1a'), _node('thor1b')]])

    code, nodes = await _get(api)
    assert code == 200
    assert nodes == [
        {'node_address': 'thor1a', 'status': 'Active', 'total_bond': '100000000', 'version': '3.10.0'},
        {'node_address': 'thor1b', 'status': 'Active', 'total_bond': '100000000', 'version': '3.10.0'},
    ]

    code, again = await _get(api)
    assert code == 200 and again == nodes
    assert api.deps.thor_connector.calls == 1


@pytest.mark.asyncio
async def test_nodes_refresh_after_ttl():
    api = _make_api([[_node('thor1a')], [_node('thor1b')]])
    await _get(api)

    api._nodes_ts -= api.NODES_CACHE_TTL + 1
    _, nodes = await _get(api)
    assert [n['node_address'] for n in nodes] == ['thor1b']


@pytest.mark.asyncio
async def test_stale_nodes_are_served_when_thornode_fails():
    api = _make_api([[_node('thor1a')], ValueError('not json'), None])
    await _get(api)

    for _ in range(2):
        api._nodes_ts -= api.NODES_CACHE_TTL + 1
        code, nodes = await _get(api)
        assert code == 200
        assert [n['node_address'] for n in nodes] == ['thor1a']

    assert api.deps.thor_connector.calls == 3


@pytest.mark.asyncio
async def test_error_without_any_node_list():
    api = _make_api([None, [_node('thor1a')]])

    code, body = await _get(api)
    assert code == 502 and 'error' in body

    # the next request asks THORNode again
    code, nodes = await _get(api)
    assert code == 200 and nodes[0]['node_address'] == 'thor1a'
