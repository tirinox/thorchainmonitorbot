import random

from services.lib.utils import random_hex, random_ip_address
from services.models.node_info import NodeInfoChanges, NodeInfo


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
        []
    )


def test_nonsense():
    all_nodes = [node_random(NodeInfo.ACTIVE) for _ in range(5)] + [node_random(NodeInfo.STANDBY) for _ in range(5)]

    c_non_1 = NodeInfoChanges([], [], [], [], all_nodes)

    assert c_non_1.is_empty
    assert c_non_1.is_nonsense

    node_white = node_random(NodeInfo.WHITELISTED)

    c_non_2 = NodeInfoChanges([node_white], [], [], [], all_nodes + [node_white])

    assert not c_non_2.is_empty
    assert c_non_2.is_nonsense

    node_good_standby = node_random(NodeInfo.STANDBY)

    c_non_3 = NodeInfoChanges(
        [node_good_standby], [], [], [], all_nodes + [node_good_standby]
    )

    assert not c_non_3.is_empty
    assert not c_non_3.is_nonsense

    c_non_4 = NodeInfoChanges([], [node_good_standby], [], [], all_nodes)

    assert not c_non_4.is_empty
    assert not c_non_4.is_nonsense

    node_good_active = node_random(NodeInfo.ACTIVE)

    c_non_5 = NodeInfoChanges([node_white], [], [node_good_active], [], all_nodes)

    assert not c_non_5.is_empty
    assert not c_non_5.is_nonsense
