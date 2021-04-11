import datetime

from services.lib.date_utils import days_ago_noon, DAY


def test_ago_noon():
    ref_date = datetime.datetime(2021, 4, 11, 9, 24, 33, 977)
    assert int(days_ago_noon(0, now=ref_date).timestamp()) == 1618131600
    assert int(days_ago_noon(1, now=ref_date).timestamp()) == 1618045200
    assert int(days_ago_noon(2, now=ref_date).timestamp()) == 1618045200 - DAY
