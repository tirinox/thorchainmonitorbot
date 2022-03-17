from services.lib.money import pretty_money, short_dollar, number_short_with_postfix


def test_short_money():
    s = short_dollar

    assert s(10) == '$10.0'
    assert s(15) == '$15.0'
    assert s(0.000151) == '$0.0002'
    assert s(0.00012) == '$0.0001'
    assert s(0) == '$0.0'

    assert s(0.1) == '$0.1'
    assert s(0.01) == '$0.01'
    assert s(0.001) == '$0.001'

    assert s(777.777) == '$777.8'
    assert s(-1234) == '-$1.2K'
    assert s(1_234_567_890_000) == '$1.2T'
    assert s(-1_234_567_890_000) == '-$1.2T'
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


def test_number_short():
    assert number_short_with_postfix(10) == '10.0'
    assert number_short_with_postfix(-10) == '-10.0'

    assert number_short_with_postfix(999) == '999.0'

    assert number_short_with_postfix(-1000) == '-1.0K'
    assert number_short_with_postfix(-1099) == '-1.1K'
    assert number_short_with_postfix(1234) == '1.2K'

    assert number_short_with_postfix(12345) == '12.3K'
    assert number_short_with_postfix(123456) == '123.5K'
    assert number_short_with_postfix(1234567) == '1.2M'
    assert number_short_with_postfix(12345678) == '12.3M'
    assert number_short_with_postfix(123456789) == '123.5M'
    assert number_short_with_postfix(1234567890) == '1.2B'
    assert number_short_with_postfix(-1234567890) == '-1.2B'

    assert number_short_with_postfix(999) == '999.0'
    assert number_short_with_postfix(999_999) == '1.0M'
    assert number_short_with_postfix(999990000000) == '1.0T'
