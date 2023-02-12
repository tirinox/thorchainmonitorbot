from services.jobs.achievement.ach_list import A
from services.jobs.achievement.tracker import AchievementsTracker


def test_minimum_threshold():
    meet = AchievementsTracker.meet_threshold

    assert meet(A.DAU, 300)
    assert meet(A.DAU, 301)
    assert not meet(A.DAU, 299)

    assert meet('_fooo_', 0)
    assert meet('_fooo_', 1)
    assert meet('_fooo_', 555)

    assert meet('_fooo_', 1, spec='fizz')

    usdc = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'

    assert meet(A.MAX_ADD_AMOUNT_USD_PER_POOL, 3_605_512.364805, spec=usdc)
    assert not meet(A.MAX_ADD_AMOUNT_USD_PER_POOL, 3_500_000, spec=usdc)
    assert meet(A.MAX_ADD_AMOUNT_USD_PER_POOL, 10_700_000, spec=usdc)

    assert meet(A.MAX_ADD_AMOUNT_USD_PER_POOL, 1, spec='unk')
    assert meet(A.MAX_ADD_AMOUNT_USD_PER_POOL, 400, spec='unk')

    assert meet(A.COIN_MARKET_CAP_RANK, 41, descending=True)
    assert meet(A.COIN_MARKET_CAP_RANK, 42, descending=True)
    assert not meet(A.COIN_MARKET_CAP_RANK, 43, descending=True)
    assert not meet(A.COIN_MARKET_CAP_RANK, 5000, descending=True)
