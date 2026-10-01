import pytest

from jobs.achievement.ach_list import ACHIEVEMENT_DESC_MAP, AchievementDescription, AchievementName

PER_POOL_KEY = 'test_per_pool'
USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'


@pytest.fixture
def per_pool_key(monkeypatch):
    """
    An achievement split by pool: no real one exists now, but the specialization machinery
    (per-pool thresholds, the ::asset:: name, the asset logo on the card) is kept for the next one
    """
    monkeypatch.setattr(AchievementName, 'TEST_PER_POOL', PER_POOL_KEY, raising=False)
    monkeypatch.setitem(ACHIEVEMENT_DESC_MAP, PER_POOL_KEY, AchievementDescription(
        PER_POOL_KEY, 'Largest ::asset:: liquidity add', prefix='$',
        thresholds={'BTC.BTC': 8_143_923, USDC: 3_605_512, 'ETH.ETH': 7_454_157},
    ))
    return PER_POOL_KEY
