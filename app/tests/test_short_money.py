from localization.manager import RussianLocalization
from services.lib.money import short_money, short_dollar


def test_short_money_simple():
    assert short_money(0) == '0.0'
    assert short_money(1000) == '1.0K'
    assert short_money(1100) == '1.1K'
    assert short_money(1151) == '1.2K'
    assert short_money(-10) == '-10.0'
    assert short_money(-10.1) == '-10.1'
    assert short_money(-10.12) == '-10.1'

    assert short_money(123456.78) == '123.5K'

    assert short_money(1_234_456) == '1.2M'
    assert short_money(10_234_456) == '10.2M'
    assert short_money(105_234_456) == '105.2M'

    assert short_money(1_405_234_456) == '1.4B'
    assert short_money(19_405_234_456) == '19.4B'
    assert short_money(999_405_234_456) == '999.4B'

    assert short_money(1_999_405_234_456) == '2.0T'
    assert short_money(1_000_999_405_234_456) == '1001.0T'


def test_short_money_signed():
    assert short_money(0, signed=True) == '0.0'
    assert short_money(1000, signed=True) == '+1.0K'
    assert short_money(1100, signed=True) == '+1.1K'
    assert short_money(1151, signed=True) == '+1.2K'
    assert short_money(-1151, signed=True) == '-1.2K'
    assert short_money(-10, signed=True) == '-10.0'
    assert short_money(-10.1, signed=True) == '-10.1'
    assert short_money(-10.12, signed=True) == '-10.1'

    assert short_money(123456.78, signed=True) == '+123.5K'

    assert short_money(1_234_456, signed=True) == '+1.2M'
    assert short_money(10_234_456, signed=True) == '+10.2M'
    assert short_money(105_234_456, signed=True) == '+105.2M'

    assert short_money(1_405_234_456, signed=True) == '+1.4B'
    assert short_money(19_405_234_456, signed=True) == '+19.4B'
    assert short_money(999_405_234_456, signed=True) == '+999.4B'
    assert short_money(-999_405_234_456, signed=True) == '-999.4B'

    assert short_money(1_999_405_234_456, signed=True) == '+2.0T'
    assert short_money(1_000_999_405_234_456, signed=True) == '+1001.0T'
    assert short_money(-1_000_999_405_234_456, signed=True) == '-1001.0T'


def test_short_money_with_fix():
    assert short_money(0, 'U', 'X') == 'U0.0X'
    assert short_money(-3000, 'U', 'X') == '-U3.0KX'
    assert short_money(-3000, 'U ', ' X') == '-U 3.0K X'
    assert short_money(34444, 'Pre ', ' Post', signed=True) == '+Pre 34.4K Post'
    assert short_money(34444, 'Pre ', ' Post') == 'Pre 34.4K Post'


def test_short_dollar():
    assert short_dollar(100) == '$100.0'
    assert short_dollar(50_000_000) == '$50.0M'
    assert short_dollar(-50_000_000) == '-$50.0M'


def test_short_rus():
    rus = RussianLocalization.SHORT_MONEY_LOC

    assert short_money(0, localization=rus) == '0.0'
    assert short_money(1000, localization=rus) == '1.0 тыс'
    assert short_money(1100, localization=rus) == '1.1 тыс'
    assert short_money(1151, localization=rus) == '1.2 тыс'
    assert short_money(-10, localization=rus) == '-10.0'
    assert short_money(-10.1, localization=rus) == '-10.1'
    assert short_money(-10.12, localization=rus) == '-10.1'

    assert short_money(123456.78, localization=rus) == '123.5 тыс'

    assert short_money(1_234_456, localization=rus) == '1.2 млн'
    assert short_money(10_234_456, localization=rus) == '10.2 млн'
    assert short_money(105_234_456, localization=rus) == '105.2 млн'

    assert short_money(1_405_234_456, localization=rus) == '1.4 млрд'
    assert short_money(19_405_234_456, localization=rus) == '19.4 млрд'
    assert short_money(999_405_234_456, localization=rus) == '999.4 млрд'

    assert short_money(1_999_405_234_456, localization=rus) == '2.0 трлн'
    assert short_money(1_000_999_405_234_456, localization=rus) == '1001.0 трлн'
    assert short_money(1_000_999_405_234_456, localization=rus, signed=True) == '+1001.0 трлн'
    assert short_money(-1_000_999_405_234_456, localization=rus) == '-1001.0 трлн'

    assert short_money(-1_000_999_405_234_456, localization=rus, signed=True, prefix='Хочу ',
                       postfix=' налом') == '-Хочу 1001.0 трлн налом'
