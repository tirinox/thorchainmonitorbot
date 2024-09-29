from lib.confwin import ConfidenceWindow


def test_clear():
    c = ConfidenceWindow(5)
    assert len(c) == 0
    for i in range(5):
        c.append(i)
    assert len(c) == 5
    c.clear()
    assert len(c) == 0


def test_size():
    c = ConfidenceWindow(5)
    c.append(1, 2, 3, 4, 5)
    assert len(c) == 5
    c.append(5)
    assert len(c) == 5
    c.append(6)
    assert len(c) == 5
    c.append(7)
    assert len(c) == 5


def test_dominance():
    c = ConfidenceWindow(5)
    for i in range(5):
        c.append(i)
    assert 0.2 == c.dominance_of(0)
    assert 0.2 == c.dominance_of(1)
    assert 0.2 == c.dominance_of(2)
    assert 0.2 == c.dominance_of(3)
    assert 0.2 == c.dominance_of(4)
    assert 0.0 == c.dominance_of(5)
    assert 0.0 == c.dominance_of(6)
    assert 0.0 == c.dominance_of(7)


def test_threshold():
    c = ConfidenceWindow(5, 0.9)
    c.append(1, 1, 2, 2, 1)
    assert c.most_common() == 1
    assert c.most_common(check_threshold=True) is None
    c.append(1, 1, 1, 1)
    assert len(c) == 5
    assert c.most_common(check_threshold=True) == 1

    c = ConfidenceWindow(10, 0.5)
    c.append(7, 7, 4, 7, 4, 7, 1, 7, 7, 7)
    assert c.most_common() == 7
    assert c.most_common(check_threshold=True) == 7
    assert len(c) == 10
    c.append(4, 4, 4, 4, 4, 4, 4, 4, 4, 4)
    assert c.most_common() == 4
    assert c.most_common(check_threshold=True) == 4


def test_full():
    c = ConfidenceWindow(500, threshold=0.001)
    assert not c.is_full
    c.append(1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 2, 4, 1)
    assert not c.is_full

    assert c.most_common(full_check=False) == 1
    assert c.most_common(full_check=True) is None
