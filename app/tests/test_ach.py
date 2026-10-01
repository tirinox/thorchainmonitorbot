from jobs.achievement.ach_list import A, Achievement
from jobs.achievement.tracker import AchievementsTracker


def meet(key, value, spec='', descending=False):
    return AchievementsTracker.meet_threshold(
        Achievement(key, value, specialization=spec, descending=descending)
    )


def test_minimum_threshold():
    assert meet(A.DAU, 300)
    assert meet(A.DAU, 301)
    assert not meet(A.DAU, 299)

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


def _block_keys(now):
    from jobs.achievement.extractor import AchievementsExtractor
    from jobs.fetch.cached.last_block import EventLastBlock
    events = AchievementsExtractor.on_block(EventLastBlock(thor_block=24_000_000, block_dict={}), now=now)
    return {e.key: e.value for e in events}


def test_block_event_is_taken_from_data():
    import asyncio
    from jobs.achievement.extractor import AchievementsExtractor
    from jobs.fetch.cached.last_block import EventLastBlock
    ev = EventLastBlock(thor_block=24_000_000, block_dict={})
    events = asyncio.run(AchievementsExtractor(deps=None).extract_events_by_type(object(), ev))
    assert any(e.key == A.BLOCK_NUMBER and e.value == 24_000_000 for e in events)


def test_anniversary_only_soon_after_the_date():
    from datetime import datetime
    # THORChain was born on 2021-04-10 12:36 (local time of the birthday timestamp)
    assert _block_keys(datetime(2026, 4, 12, 12, 0).timestamp()) == {A.BLOCK_NUMBER: 24_000_000, A.ANNIVERSARY: 5}
    assert _block_keys(datetime(2026, 10, 1, 12, 0).timestamp()) == {A.BLOCK_NUMBER: 24_000_000}
    assert _block_keys(datetime(2026, 4, 9, 12, 0).timestamp()) == {A.BLOCK_NUMBER: 24_000_000}
