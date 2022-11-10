import pytest

from services.lib.date_utils import seconds_human, DAY, HOUR, MINUTE


@pytest.mark.parametrize(('x', 's'), [
    (1, '1 sec'),
    (2, '2 sec'),
    (0, 'just now'),
    (60, '1 min'),
    (72, '1 min 12 sec'),
    (HOUR * 2 + MINUTE * 45, '2 hours 45 min'),
    (HOUR * 2 + MINUTE * 45 + 59, '2 hours 45 min'),

    (DAY, '1 day'),
    (7 * DAY, '7 days'),
    (DAY + MINUTE * 59 + 45, '1 day'),
    (DAY + HOUR + 45, '1 day 1 hour'),
    (DAY * 3 + 20 * HOUR + 45, '3 days 20 hours'),
    (12 * DAY + 59 * MINUTE, '12 days'),
    (30 * DAY, '1 month'),
    (60 * DAY, '2 months'),
    (61 * DAY, '2 months 1 day'),
    (69 * DAY + 23 * HOUR, '2 months 9 days'),

    (365 * DAY, '1 year'),
    (365 * DAY + 30 * DAY + 10 * HOUR, '1 year 1 month'),
    (365 * DAY + 30 * DAY, '1 year 1 month'),
    (365 * DAY + 70 * DAY + 10 * HOUR, '1 year 2 months 10 days'),
    (365 * DAY + 70 * DAY, '1 year 2 months 10 days'),

    # negative
    (-1, '-1 sec'),
    (-DAY, '-1 day'),
    (-365 * DAY - 70 * DAY, '-1 year 2 months 10 days'),
])
def test_seconds_human(x, s):
    assert seconds_human(x) == s
