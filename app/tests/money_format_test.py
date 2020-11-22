from services.lib.money import pretty_money, short_money


def test_short_money():
    s = short_money

    assert s(10) == '$10.0'
    assert s(0) == '$0.0'
    assert s(0.1) == '$0.1'
    assert s(777.777) == '$777.8'
    assert s(-1234) == '-$1.2K'
    assert s(1_234_567_890_000) == '$1234.6B'
    assert s(-1_234_567_890_000) == '-$1234.6B'
    assert s(10_333_777) == '$10.3M'
    assert s(-10_333_777) == '-$10.3M'


def test_pretty_money():
    p = pretty_money
    assert p(10, 'B') == 'B10'
    assert p(1234) == '1,234'
    assert p(1234.5) == '1,234'
    assert p(-10_777_888, '$') == '-$10,777,888'
    assert p(10_777_888, '$') == '$10,777,888'
    assert p(10_777_888_999, '$') == '$10,777,888,999'
