import pytest

from jobs.achievement.milestones import Milestones, MilestonesEveryInt

m = Milestones()


@pytest.mark.parametrize('x, expected', [
    (1, 2),
    (2, 5),
    (3, 5),
    (5, 10),
    (8, 10),
    (1000, 2000),
    (888, 1000),
    (999, 1000),
    (1001, 2000),
])
def test_next(x, expected):
    assert m.next(x) == expected


@pytest.mark.parametrize('x, expected', [
    (1, 1),
    (2, 2),
    (3, 2),
    (5, 5),
    (6, 5),
    (10, 10),
    (999, 500),
    (1000, 1000),
    (1104, 1000),
    (1e6, 1e6),
])
def test_prev(x, expected):
    assert m.previous(x) == expected


every_m = Milestones(Milestones.EVERY_DIGIT_PROGRESSION)


@pytest.mark.parametrize('x, expected', [
    (5, 5),
    (9, 9),
    (10, 10),
    (100, 100),
])
def test_prev_every(x, expected):
    assert every_m.previous(x) == expected


@pytest.mark.parametrize('x, expected', [
    (10, 20),
    (9, 10),
    (1, 2),
    (3, 4),
    (1000, 2000),
])
def test_next_every(x, expected):
    assert every_m.next(x) == expected


m_int = MilestonesEveryInt()


@pytest.mark.parametrize('x, expected', [
    (1, 1),
    (2, 2),
    (10000, 10000),
])
def test_previous_every_int(x, expected):
    assert m_int.previous(x) == expected


@pytest.mark.parametrize('x, expected', [
    (10, 11),
    (19, 20),
    (1, 2),
    (1000, 1001),
])
def test_next_every_int(x, expected):
    assert m_int.next(x) == expected
