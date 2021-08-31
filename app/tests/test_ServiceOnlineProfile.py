from services.notify.personal.node_online import ServiceOnlineProfile


def boolz(v):
    return list(map(bool, v))


def test_empty():
    p = ServiceOnlineProfile.from_points([], 'test')
    assert p.num_points == 0
    assert p.num_last_silent_points == 0
    assert p.num_online_points == 0
    assert p.recent_offline_ratio == 0.0
    assert p.online_ratio == 0.0


def test_good():
    p = ServiceOnlineProfile.from_points(boolz([1, 1, 1, 1, 1]), 'test')
    assert p.num_points == p.num_online_points == 5
    assert p.online_ratio == 1.0
    assert p.recent_offline_ratio == 0.0
    assert p.num_last_silent_points == 0


def test_common_1():
    p = ServiceOnlineProfile.from_points(boolz([0, 1, 0, 1, 1, 0, 0, 0, 0, 0]), 'test')
    assert p.num_points == 10
    assert p.num_online_points == 3
    assert p.num_last_silent_points == 5
    assert p.recent_offline_ratio == 0.5
    assert p.online_ratio == 0.3


def test_common_2():
    p = ServiceOnlineProfile.from_points(boolz([0, 1, 0, 1, 1, 0, 1, 1, 0, 1]), 'test')
    assert p.num_points == 10
    assert p.num_online_points == 6
    assert p.num_last_silent_points == 0
    assert p.recent_offline_ratio == 0.0
    assert p.online_ratio == 0.6


def test_common_3():
    p = ServiceOnlineProfile.from_points(boolz([0, 1, 0, 1, 1, 0, 1, 1, 1, 0]), 'test')
    assert p.num_points == 10
    assert p.num_online_points == 6
    assert p.num_last_silent_points == 1
    assert p.recent_offline_ratio == 0.1
    assert p.online_ratio == 0.6
