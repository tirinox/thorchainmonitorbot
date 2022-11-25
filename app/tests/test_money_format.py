import pytest

from services.lib.money import pretty_money, short_dollar, short_money, detect_decimal_digits, format_percent, \
    parse_short_number
from services.lib.texts import up_down_arrow


def test_short_money():
    s = short_dollar

    assert s(10) == '$10.0'
    assert s(15) == '$15.0'
    assert s(0.000151) == '$0.000151'
    assert s(0.00012) == '$0.00012'
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

    assert short_money(0.0000095) == '0.0000095'
    assert short_money(0.012) == '0.012'
    assert short_money(1) == '1.0'
    assert short_money(2) == '2.0'
    assert short_money(1.456) == '1.5'


@pytest.mark.parametrize("x, y", [
    (0, '0'),
    (0.01, '0.01'),
    (2, '2'),
    (55, '55'),
    (1000, '1K'),
    (1200, '1K'),
    (1900, '1K'),
    (2000, '2K'),
    (2001, '2K'),
    (2e6 + 333888, '2M'),
])
def test_short_money_int(x, y):
    assert short_money(x, integer=True) == y
    assert short_money(x, prefix='$', postfix='Y', integer=True) == f'${y}Y'


def test_pretty_money():
    p = pretty_money
    assert p(10, 'B') == 'B10'
    assert p(1234) == '1,234'
    assert p(1234.5) == '1,234'
    assert p(-10_777_888, '$') == '-$10,777,888'
    assert p(10_777_888, '$') == '$10,777,888'
    assert p(10_777_888_999, '$') == '$10,777,888,999'

    assert p(0.1926640162) == '0.193'


def test_arrow():
    assert up_down_arrow(1.0, 1.1926640162, percent_delta=True) == '↑ +0.193%'


@pytest.mark.parametrize("x, digits", [
    (10, 0),
    (11.1, 0),
    (5.55, 0),
    (1.0, 0),
    (0.9, 1),
    (0.11, 1),
    (0.011, 2),
    (0.099, 2),
    (0.005, 3),
    (0.000342124, 4),
    (0.02792164, 0.028),
    (0.316261111, 0.32),
])
def test_detect_decimals(x, digits):
    assert detect_decimal_digits(x) == digits


@pytest.mark.parametrize("x, total, out, threshold", [
    (0.5, 100.0, '0 %', 1.0),
    (0.0, 100.0, '0 %', 0.1),
    (0.99, 100.0, '0 %', 1.0),
    (1.0, 100.0, '1.0 %', 1.0),
    (25.0, 50.0, '50.0 %', 0.0),
])
def test_percent(x, total, out, threshold):
    assert format_percent(x, total, threshold=threshold) == out


@pytest.mark.parametrize("x, y", [
    ("0", 0),
    ("   1 \t ", 1),
    ("0.0991", 0.0991),
    ("500_000.123", 500_000.123),
    ("1k", 1000),
    (" 5K", 5000),
    ("3.3M", 3_300_000),
    ("5.25b", 5_250_000_000),
])
def test_parse_short_number(x, y):
    assert parse_short_number(x) == y
