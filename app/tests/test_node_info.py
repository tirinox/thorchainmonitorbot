import json
import random

import pytest

from services.lib.utils import random_hex, random_ip_address
from services.models.node_info import NodeSetChanges, NodeInfo


def node_random(status=NodeInfo.ACTIVE) -> NodeInfo:
    return NodeInfo(
        status,
        f'thor{random_hex()}',
        random.randint(100, 100000),
        random_ip_address(),
        'v.55.0',
        random.randint(0, 1000),
        random.randint(0, 1000),
        False, False, 123456,
        100, []
    )


def test_nonsense():
    all_nodes = [node_random(NodeInfo.ACTIVE) for _ in range(5)] + [node_random(NodeInfo.STANDBY) for _ in range(5)]

    c_non_1 = NodeSetChanges([], [], [], [], all_nodes, all_nodes)

    assert c_non_1.is_empty
    assert c_non_1.is_nonsense

    node_white = node_random(NodeInfo.WHITELISTED)

    c_non_2 = NodeSetChanges([node_white], [], [], [], all_nodes + [node_white], all_nodes)

    assert not c_non_2.is_empty
    assert c_non_2.is_nonsense

    node_good_standby = node_random(NodeInfo.STANDBY)

    c_non_3 = NodeSetChanges(
        [node_good_standby], [], [], [], all_nodes + [node_good_standby],
        all_nodes
    )

    assert not c_non_3.is_empty
    assert not c_non_3.is_nonsense

    c_non_4 = NodeSetChanges([], [node_good_standby], [], [], all_nodes, all_nodes)

    assert not c_non_4.is_empty
    assert not c_non_4.is_nonsense

    node_good_active = node_random(NodeInfo.ACTIVE)

    c_non_5 = NodeSetChanges([node_white], [], [node_good_active], [], all_nodes, all_nodes)

    assert not c_non_5.is_empty
    assert not c_non_5.is_nonsense


@pytest.fixture
def load_node_info_from_file():
    def loader(file='./sample_data/nodes_7_9_22.json'):
        with open(file, 'r') as f:
            data = json.load(f)
        return [NodeInfo.from_json(piece) for piece in data]

    return loader


def test_loader(load_node_info_from_file):
    nodes = load_node_info_from_file()
    assert len(nodes) == 180
    assert len([n for n in nodes if n.is_active]) == 95


def test_active_version(load_node_info_from_file):
    nodes = load_node_info_from_file()
    node_changes = NodeSetChanges(
        [], [], [], [], nodes, nodes
    )

    assert any(n for n in nodes if n.version == '1.95.1')

    assert node_changes.max_active_version == '1.96.0'
    assert node_changes.current_active_version == '1.95.0'
