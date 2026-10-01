import os
from datetime import datetime

import pytest

from comm.localization.achievements.ach_eng import AchievementsEnglishLocalization
from comm.localization.achievements.ach_rus import AchievementsRussianLocalization
from comm.localization.achievements.ach_tw_eng import AchievementsTwitterEnglishLocalization
from comm.picture.achievement_card import build_achievement_card, BACKGROUND_STYLE, RUNIC_GLYPHS, BALLOON_GLYPHS
from jobs.achievement.ach_list import A, Achievement, ACHIEVEMENT_DESC_MAP, AchievementName
from lib.date_utils import DAY

STATIC_ACH = 'data/renderer/static/img/achievement'
USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
TS = datetime(2026, 10, 1, 12, 0).timestamp()


@pytest.fixture
def en():
    return AchievementsEnglishLocalization()


@pytest.fixture
def ru():
    return AchievementsRussianLocalization()


@pytest.mark.parametrize('loc_class', [
    AchievementsEnglishLocalization, AchievementsRussianLocalization, AchievementsTwitterEnglishLocalization,
])
def test_every_achievement_is_translated(loc_class):
    loc = loc_class()
    missing = [k for k in AchievementName.all_keys() if not loc.TRANSLATION_MAP.get(k)]
    assert not missing
    for key in AchievementName.all_keys():
        assert loc.get_achievement_description(key).description


def test_every_background_exists():
    for desc in ACHIEVEMENT_DESC_MAP.values():
        assert desc.background in BACKGROUND_STYLE, desc.key
    for bg in BACKGROUND_STYLE:
        assert os.path.isfile(f'{STATIC_ACH}/bg/{bg}'), bg


def test_every_glyph_exists():
    for file in RUNIC_GLYPHS.values():
        assert os.path.isfile(f'{STATIC_ACH}/runic/{file}'), file
    for file in BALLOON_GLYPHS.values():
        assert os.path.isfile(f'{STATIC_ACH}/balloon/{file}'), file


def test_round_milestones_lose_zero_fraction(en):
    def fmt(key, v):
        a = Achievement(key, v)
        return en.format_value(v, a, en.get_achievement_description(key))

    assert fmt(A.MARKET_CAP_USD, 2_000_000_000) == '$2B'
    assert fmt(A.MARKET_CAP_USD, 2_500_000_000) == '$2.5B'
    assert fmt(A.WALLET_COUNT, 100_000) == '100K'
    assert fmt(A.TOTAL_BOND, 50_000_000) == '50M ᚱ'
    assert fmt(A.NODE_COUNT, 100) == '100'


def test_asset_name_is_short(en, ru):
    a = Achievement(A.MAX_ADD_AMOUNT_USD_PER_POOL, 8_200_000, 5_000_000, TS, specialization=USDC)
    assert build_achievement_card(a, en)['title'] == 'Added ETH.USDC in a single TX'
    assert 'ETH.USDC in a single TX' in en.notification_achievement_unlocked(a)
    assert '0XA0B8' not in ru.notification_achievement_unlocked(a)

    card = build_achievement_card(a, en)
    assert card['asset_logo'] == USDC


def test_card_default(en):
    a = Achievement(A.MARKET_CAP_USD, 2_134_000_000, 2_000_000_000, TS, 1_000_000_000, TS - 40 * DAY)
    card = build_achievement_card(a, en)
    assert card['number_label'] == 'More than'
    assert card['number_text'] == '$2B'
    assert [g['src'] for g in card['glyphs']] == ['runic/bw_USD.png', 'runic/bw_2.png', 'runic/bw_B.png']
    assert card['date'] == 'October 1, 2026'
    assert card['stats'] == [
        {'label': 'Previous', 'value': '$1B', 'sub': '1 month 10 days ago'},
        {'label': 'Now', 'value': '$2,134,000,000', 'sub': ''},
        {'label': 'Next goal', 'value': '$5B', 'sub': ''},
    ]


def test_card_first_milestone_has_no_previous(en):
    a = Achievement(A.RUNEPOOL_VALUE_USD, 20_000_000, 20_000_000, TS)
    card = build_achievement_card(a, en)
    # "Now" equals the milestone, so only the next goal is left
    assert card['stats'] == [{'label': 'Next goal', 'value': '$50M', 'sub': ''}]


def test_card_rank(en):
    a = Achievement(A.COIN_MARKET_CAP_RANK, 30, 31, TS, 33, TS - 40 * DAY, descending=True)
    card = build_achievement_card(a, en)
    assert card['number_label'] == 'Top'
    assert card['number_text'] == '30'
    assert [s['value'] for s in card['stats']] == ['#33', '#29']

    top1 = Achievement(A.COIN_MARKET_CAP_RANK, 1, 2, TS, 2, TS - 40 * DAY, descending=True)
    assert [s['value'] for s in build_achievement_card(top1, en)['stats']] == ['#2']


def test_card_anniversary_ru(ru):
    a = Achievement(A.ANNIVERSARY, 6, 6, TS, 5, TS - 365 * DAY)
    card = build_achievement_card(a, ru)
    assert card['number_font'] == 'balloon'
    assert card['glyphs'] == [{'kind': 'glyph', 'src': 'balloon/6.png'}]
    assert card['stats'] == []
    assert card['subtitle'] == '6 лет с первого блока'
    assert card['date'] == '1 октября 2026'


def test_ago_is_translated(ru):
    a = Achievement(A.WEEKLY_PROTOCOL_REVENUE_USD, 1_030_000, 1_000_000, TS, 500_000, TS - 40 * DAY)
    card = build_achievement_card(a, ru)
    assert card['stats'][0] == {'label': 'Было', 'value': '$500K', 'sub': '1 мес 10 дн назад'}
    assert '1 мес 10 дн назад' in ru.notification_achievement_unlocked(a)


def test_next_milestone():
    assert Achievement(A.MARKET_CAP_USD, 2_134_000_000).get_next_milestone() == 5_000_000_000
    assert Achievement(A.WALLET_COUNT, 104_500).get_next_milestone() == 200_000
    assert Achievement(A.COIN_MARKET_CAP_RANK, 30, descending=True).get_next_milestone() == 29
    assert Achievement(A.COIN_MARKET_CAP_RANK, 1, descending=True).get_next_milestone() == 0
