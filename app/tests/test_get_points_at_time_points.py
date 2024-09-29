from lib.date_utils import now_ts
from notify.personal.helpers import get_points_at_time_points


def test_1():
    n = 100
    now = now_ts()
    data = [(now - n + i, i) for i in range(1, n)]
    ago_list = [
        10, 20, 45
    ]

    assert not get_points_at_time_points(data, [])
    assert not get_points_at_time_points([], ago_list)

    r = get_points_at_time_points(data, ago_list)
    print(r)
    for ago in ago_list:
        assert now - ago - r[ago][0] < 0.1
        assert r[ago][1] == n - ago
