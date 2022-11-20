from services.lib.utils import most_common_and_other


def test_most_common_and_other():
    r = most_common_and_other([5] * 10 + [2] * 5 + [1] * 7 + [3] * 2 + [4] * 6, 3, 'other')
    assert r == [(5, 10), (1, 7), (4, 6), ('other', 7)]

    r = most_common_and_other([5] * 10 + [2] * 5 + [1] * 7 + [3] * 2 + [4] * 6, 10, 'foo')
    assert r == [(5, 10), (1, 7), (4, 6), (2, 5), (3, 2), ('foo', 0)]

    r = most_common_and_other([5] * 10 + [2] * 5 + [1] * 7 + [3] * 2 + [4] * 6, 10, None)
    assert r == [(5, 10), (1, 7), (4, 6), (2, 5), (3, 2)]

    r = most_common_and_other([], 5, 'foo')
    assert r == [('foo', 0)]

    r = most_common_and_other([], 5, '')
    assert r == []
