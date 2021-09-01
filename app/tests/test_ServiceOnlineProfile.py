from services.jobs.fetch.thormon import ThorMonNode
from services.notify.personal.node_online import ServiceOnlineProfile


def boolz(v):
    return 'OK' if v else 'BAD'


def build_helper(arr: list):
    n = len(arr)
    return [(float(ts), bool(status)) for ts, status in zip(range(n), arr)]


def test_empty():
    p = ServiceOnlineProfile.from_points([], 'test')
    assert p.num_points == 0
    assert p.num_last_silent_points == 0
    assert p.num_online_points == 0
    assert p.recent_offline_ratio == 0.0
    assert p.online_ratio == 0.0


def test_good():
    p = ServiceOnlineProfile.from_points(build_helper([1, 1, 1, 1, 1]), 'test')
    assert p.num_points == p.num_online_points == 5
    assert p.online_ratio == 1.0
    assert p.recent_offline_ratio == 0.0
    assert p.num_last_silent_points == 0


def test_common_1():
    p = ServiceOnlineProfile.from_points(build_helper([0, 1, 0, 1, 1, 0, 0, 0, 0, 0]), 'test')
    assert p.num_points == 10
    assert p.num_online_points == 3
    assert p.num_last_silent_points == 5
    assert p.recent_offline_ratio == 0.5
    assert p.online_ratio == 0.3


def test_common_2():
    p = ServiceOnlineProfile.from_points(build_helper([0, 1, 0, 1, 1, 0, 1, 1, 0, 1]), 'test')
    assert p.num_points == 10
    assert p.num_online_points == 6
    assert p.num_last_silent_points == 0
    assert p.recent_offline_ratio == 0.0
    assert p.online_ratio == 0.6


def test_common_3():
    p = ServiceOnlineProfile.from_points(build_helper([0, 1, 0, 1, 1, 0, 1, 1, 1, 0]), 'test')
    assert p.num_points == 10
    assert p.num_online_points == 6
    assert p.num_last_silent_points == 1
    assert p.recent_offline_ratio == 0.1
    assert p.online_ratio == 0.6


def test_filter():
    p = ServiceOnlineProfile.from_points(build_helper([0, 1, 0, 1, 1, 0, 1, 1, 1, 0]), 'test').filter_age(3)
    assert p.num_points == 4
    assert p.num_online_points == 3
    assert p.num_last_silent_points == 1
    assert p.online_ratio == 0.75
    assert p.recent_offline_ratio == 0.25


def test_offline_time():
    p = ServiceOnlineProfile.from_points(build_helper([0, 1, 0, 1, 1, 0, 1, 1, 1, 1]), 'test')
    assert p.calc_offline_time(now=9) == 0
    assert p.calc_offline_time(now=10) == 0

    p = ServiceOnlineProfile.from_points(build_helper([0, 1, 0, 1, 1, 0, 1, 1, 0, 0]), 'test')
    assert p.calc_offline_time(now=9) == 1.0


def build_helper_node(arr: list, service='rpc'):
    n = len(arr)
    return [
        (
            float(ts),
            ThorMonNode.from_json({service: boolz(status)})
        ) for ts, status in zip(range(n), arr)
    ]


def test_load():
    p = ServiceOnlineProfile.from_thormon_nodes(build_helper_node([
        True, True, False, False, False, True, True, True, False, False
    ]), 'rpc')

    assert p.num_points == 10
    assert p.num_last_silent_points == 2
    assert p.recent_offline_ratio == 0.2
    assert p.online_ratio == 0.5
    assert p.num_online_points == 5
