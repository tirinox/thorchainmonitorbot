from services.lib.config import Config
from services.lib.depcont import DepContainer
from services.models.thormon import ThorMonAnswer, ThorMonNode, ThorMonChainHeight
from services.notify.personal import ChainHeightTracker


def make_node_h(btc, eth):
    return ThorMonNode(
        '', '', 0, 0, 0, '', '', {
            'BTC': ThorMonChainHeight('BTC', btc),
            'ETH': ThorMonChainHeight('ETH', eth),
        }, False, False, 0, 0, True, True, True, True, {}
    )


def test_committee():
    tracker = ChainHeightTracker(deps=DepContainer(cfg=Config(data={})))

    # class ThorMonAnswer(NamedTuple):
    #     last_block: int
    #     next_churn: int
    #     nodes: List[ThorMonNode]
    thor_mon = ThorMonAnswer(0, 0, [
        make_node_h(10, 10),
        make_node_h(14, 12),
        make_node_h(10, 10),
        make_node_h(10, 12),
        make_node_h(14, 12),
        make_node_h(14, 11),
        make_node_h(10, 11),
        make_node_h(10, 11),
        make_node_h(10, 11),
    ])

    assert tracker.estimate_block_height_maximum(thor_mon) == {'BTC': 14, 'ETH': 12}

    assert tracker.estimate_block_height_most_common(thor_mon) == {'BTC': 10, 'ETH': 11}

    assert tracker.estimate_block_height_max_by_committee(thor_mon, 1) == {'BTC': 14, 'ETH': 12}
    assert tracker.estimate_block_height_max_by_committee(thor_mon, 2) == {'BTC': 14, 'ETH': 12}
    assert tracker.estimate_block_height_max_by_committee(thor_mon, 3) == {'BTC': 14, 'ETH': 12}
    assert tracker.estimate_block_height_max_by_committee(thor_mon, 4) == {'BTC': 10, 'ETH': 11}
