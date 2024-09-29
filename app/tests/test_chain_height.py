from lib.config import Config
from lib.depcont import DepContainer
from models.node_info import NodeInfo
from notify.personal.chain_height import ChainHeightTracker


def make_node_h(btc, eth):
    return NodeInfo(observe_chains=[
        {'chain': 'BTC', 'height': btc},
        {'chain': 'ETH', 'height': eth},
    ])


def test_committee():
    tracker = ChainHeightTracker(deps=DepContainer(cfg=Config(data={})))

    nodes = [
        make_node_h(10, 10),
        make_node_h(14, 12),
        make_node_h(10, 10),
        make_node_h(10, 12),
        make_node_h(14, 12),
        make_node_h(14, 11),
        make_node_h(10, 11),
        make_node_h(10, 11),
        make_node_h(10, 11),
    ]

    assert tracker.estimate_block_height_maximum(nodes) == {'BTC': 14, 'ETH': 12}

    assert tracker.estimate_block_height_most_common(nodes) == {'BTC': 10, 'ETH': 11}

    assert tracker.estimate_block_height_max_by_committee(nodes, 1) == {'BTC': 14, 'ETH': 12}
    assert tracker.estimate_block_height_max_by_committee(nodes, 2) == {'BTC': 14, 'ETH': 12}
    assert tracker.estimate_block_height_max_by_committee(nodes, 3) == {'BTC': 14, 'ETH': 12}
    assert tracker.estimate_block_height_max_by_committee(nodes, 4) == {'BTC': 10, 'ETH': 11}
