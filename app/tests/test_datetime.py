import datetime

from services.lib.date_utils import days_ago_noon, DAY, full_years_old_ts, YEAR, HOUR, MINUTE


def test_ago_noon():
    ref_date = datetime.datetime(2021, 4, 11, 9, 24, 33, 977)
    assert int(days_ago_noon(0, now=ref_date).timestamp()) == 1618131600
    assert int(days_ago_noon(1, now=ref_date).timestamp()) == 1618045200
    assert int(days_ago_noon(2, now=ref_date).timestamp()) == 1618045200 - DAY


def test_full_years_old():
    ref_date = 1548186000
    assert full_years_old_ts(ref_date, ref_date) == 0
    assert full_years_old_ts(ref_date - YEAR, ref_date - HOUR) == 0
    assert full_years_old_ts(ref_date - YEAR, ref_date) == 1
    assert full_years_old_ts(ref_date - YEAR * 2, ref_date) == 2

    assert full_years_old_ts(1548186000, 1642880400) == 3
    assert full_years_old_ts(1548186000, 1642880400 - MINUTE) == 2
    assert full_years_old_ts(1488275400, 1646041800) == 5
    assert full_years_old_ts(1488275400, 1646041800 - MINUTE) == 4

    assert full_years_old_ts(1262343000, 1674417617) == 13
    assert full_years_old_ts(1262343000, 1672563000) == 12
