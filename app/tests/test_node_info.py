import random

from lib.utils import random_hex, random_ip_address
from models.node_info import NodeSetChanges, NodeInfo


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


def _node(status, address, bond, award=0.0, active_since=0):
    return NodeInfo(status, address, bond, current_award=award, active_block_height=active_since)


def _churn(prev_nodes, curr_nodes, block_no):
    from jobs.node_churn import NodeChurnDetector
    changes = NodeChurnDetector.extract_changes(curr_nodes, prev_nodes)
    changes.block_no = block_no
    return changes


def test_churn_rewards():
    a = NodeInfo.ACTIVE
    prev = [
        _node(a, 'thor1', 1_000_000, award=3000, active_since=10_000),
        _node(a, 'thor2', 2_000_000, award=5000, active_since=20_000),  # joined at the previous churn
        _node(a, 'thor3', 1_000_000, award=0, active_since=10_000),  # no reward
        _node(NodeInfo.STANDBY, 'thor4', 500_000, award=777),  # standby does not count
    ]
    curr = [
        _node(a, 'thor1', 1_003_000, active_since=10_000),
        _node(a, 'thor2', 2_005_000, active_since=20_000),
        _node(NodeInfo.STANDBY, 'thor3', 1_000_000),
        _node(a, 'thor4', 500_000, active_since=30_000),
    ]
    r = _churn(prev, curr, block_no=30_000).churn_rewards

    assert r.total_rune == 8000
    assert r.n_nodes == 2
    assert r.average_rune == 4000
    assert r.total_bond == 4_000_000
    assert r.period_blocks == 10_000
    assert r.period_sec == 60_000
    assert abs(r.apr - 8000 / 4_000_000 * 525.6 * 100) < 1e-9


def test_churn_rewards_unknown_period():
    a = NodeInfo.ACTIVE
    prev = [_node(a, 'thor1', 1_000_000, award=3000)]  # no active_block_height (old snapshot)
    curr = [_node(NodeInfo.STANDBY, 'thor1', 1_000_000), _node(a, 'thor2', 1_000_000, active_since=30_000)]
    r = _churn(prev, curr, block_no=30_000).churn_rewards
    assert r.total_rune == 3000 and r.period_blocks == 0 and r.apr is None

    prev = [_node(a, 'thor1', 1_000_000, award=3000, active_since=29_900)]  # too short to tell an APR
    r = _churn(prev, curr, block_no=30_000).churn_rewards
    assert r.period_blocks == 100 and r.apr is None

    assert _churn([], curr, block_no=30_000).churn_rewards.total_rune == 0


def test_churn_started_text():
    from comm.localization.eng_base import EnglishLocalization
    from comm.localization.rus import RussianLocalization
    from comm.localization.twitter_eng import TwitterEnglishLocalization
    from lib.config import Config
    from models.node_info import AlertNodeChurn

    a = NodeInfo.ACTIVE
    prev = [
        _node(a, 'thor1', 1_000_000, award=3000, active_since=10_000),
        _node(a, 'thor2', 2_000_000, award=5000, active_since=20_000),
        _node(NodeInfo.STANDBY, 'thor3', 1_500_000),
    ]
    curr = [
        _node(NodeInfo.STANDBY, 'thor1', 1_003_000),
        _node(a, 'thor2', 2_005_000, active_since=20_000),
        _node(a, 'thor3', 1_500_000, active_since=30_000),
    ]
    changes = _churn(prev, curr, block_no=30_000)
    changes.vaults_migrating = True
    event = AlertNodeChurn(changes, finished=False, with_picture=False, usd_per_rune=2.0)

    cfg = Config(name='./tests/test_config.yaml')
    en = EnglishLocalization(cfg).notification_churn_started(event)
    assert '#30000' in en
    assert '+1.5M' in en and '-1.0M' in en  # bond in and out
    assert '8.0K' in en and '$16.0K' in en  # rewards paid
    assert '4.0K' in en and '$8.0K' in en  # average reward
    assert 'APR' in en and '140.2 %' in en

    ru = RussianLocalization(cfg).notification_churn_started(event)
    assert 'Выплачено наград' in ru and '140.2 %' in ru

    tw = TwitterEnglishLocalization(cfg).notification_churn_started(event)
    assert '<b>' not in tw and '8.0K' in tw and '140.2 %' in tw

    # no price: no dollars
    en = EnglishLocalization(cfg).notification_churn_started(AlertNodeChurn(changes, False, False))
    assert '$' not in en and '8.0K' in en
