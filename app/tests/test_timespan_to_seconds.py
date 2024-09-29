from lib.date_utils import parse_timespan_to_seconds, HOUR, MINUTE, DAY


def test_1():
    f = parse_timespan_to_seconds
    assert f('1') == 1
    assert f('') == 0
    assert f(' 50m ') == 50 * MINUTE
    assert f('1H') == HOUR
    assert f('2d') == DAY * 2
    assert f('2d 5') == DAY * 2 + 5
    assert f('2d 5s') == DAY * 2 + 5

    assert f('6s 7m 4h 8d') == 6 + 7 * MINUTE + 4 * HOUR + 8 * DAY


def test_float():
    f = lambda x: parse_timespan_to_seconds(x, do_float=True)

    assert f('1.1') == 1.1
    assert f(' 1.1 \n  ') == 1.1
    assert f('0') == 0.0

    assert f('22.23') == 22.23

    assert f('11.4s 50.1m') == 11.4 + 50.1 * MINUTE
    assert f('11.4s\t50.1m\n') == 11.4 + 50.1 * MINUTE

    assert f('6.1s 7.2m 4.3h 8.4d') == 6.1 + 7.2 * MINUTE + 4.3 * HOUR + 8.4 * DAY
