from services.jobs.achievement.ach_list import A
from services.jobs.achievement.tracker import AchievementsTracker


def test_minimum_threshold():
    f = AchievementsTracker.get_minimum
    assert f(A.DAU) == 300
    assert f('_fooo_') == 1
    assert f('_fooo_', default=555) == 555

    assert f('_fooo_', 'fizz') == 1

    assert f(A.MAX_ADD_AMOUNT_USD_PER_POOL, 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48') == 3605512.364805
    assert f(A.MAX_ADD_AMOUNT_USD_PER_POOL, 'unk', 10) == 10
