import pytest

from services.jobs.achievements import Milestones

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
    (1e6, 1e6),
])
def test_prev(x, expected):
    assert m.previous(x) == expected
