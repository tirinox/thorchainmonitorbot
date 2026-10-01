"""
Writes a renderer demo for every achievement in every card language into renderer/demo/achievements/.
The renderer container has no bot dependencies, so the card parameters are built here and saved as JSON.
Run it again after adding an achievement or changing the card: make renderer-demos
"""
import json
import os
import shutil
from datetime import datetime

from comm.localization.achievements.ach_eng import AchievementsEnglishLocalization
from comm.localization.achievements.ach_rus import AchievementsRussianLocalization
from comm.picture.achievement_card import build_achievement_card, ACHIEVEMENT_TEMPLATE
from jobs.achievement.ach_list import Achievement, A, ACHIEVEMENT_DESC_MAP
from lib.date_utils import DAY

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'renderer', 'demo', 'achievements')

# a fixed date keeps the files the same between runs
DEMO_TS = datetime(2026, 10, 1, 12, 0).timestamp()

DEFAULT_VALUE = 12_345

# key => current value, or (value, specialization); a key can be listed several times
DEMO_VALUES = [
    (A.DAU, 2_340),
    (A.MAU, 61_200),
    (A.WALLET_COUNT, 712_400),
    (A.DAILY_TX_COUNT, 54_300),
    (A.DAILY_VOLUME, 212_000_000),
    (A.BLOCK_NUMBER, 23_412_000),
    (A.ANNIVERSARY, 5),
    (A.SWAP_COUNT_TOTAL, 31_250_000),
    (A.SWAP_COUNT_24H, 62_400),
    (A.SWAP_COUNT_30D, 1_240_000),
    (A.SWAP_VOLUME_TOTAL_RUNE, 12_340_000_000),
    (A.ADD_LIQUIDITY_COUNT_TOTAL, 1_120_000),
    (A.ADD_LIQUIDITY_VOLUME_TOTAL, 5_230_000_000),
    (A.NODE_COUNT, 120),
    (A.ACTIVE_NODE_COUNT, 104),
    (A.TOTAL_ACTIVE_BOND, 52_400_000),
    (A.TOTAL_BOND, 61_000_000),
    (A.TOTAL_MIMIR_VOTES, 2_150),
    (A.MARKET_CAP_USD, 2_134_000_000),
    (A.TOTAL_POOLS, 52),
    (A.TOTAL_ACTIVE_POOLS, 31),
    (A.COIN_MARKET_CAP_RANK, 30),
    (A.MAX_SWAP_AMOUNT_USD, 21_300_000),
    (A.MAX_ADD_AMOUNT_USD, 41_000_000),
    (A.POL_VALUE_RUNE, 21_500_000),
    (A.MAX_ADD_AMOUNT_USD_PER_POOL, (8_200_000, 'BTC.BTC')),
    (A.MAX_ADD_AMOUNT_USD_PER_POOL, (5_400_000, 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48')),
    (A.BTC_IN_VAULT, 2_140),
    (A.ETH_IN_VAULT, 21_500),
    (A.STABLES_IN_VAULT, 54_000_000),
    (A.TOTAL_VALUE_LOCKED, 512_000_000),
    (A.WEEKLY_PROTOCOL_REVENUE_USD, 1_120_000),
    (A.WEEKLY_AFFILIATE_REVENUE_USD, 213_000),
    (A.WEEKLY_SWAP_VOLUME, 2_340_000_000),
    (A.TRADE_BALANCE_TOTAL_USD, 23_400_000),
    (A.TRADE_ASSET_HOLDERS_COUNT, 1_240),
    (A.TRADE_ASSET_SWAPS_COUNT, 2_150_000),
    (A.TRADE_ASSET_SWAPS_VOLUME, 5_420_000_000),
    (A.TRADE_ASSET_MOVE_COUNT, 112_000),
    (A.TRADE_ASSET_LARGEST_DEPOSIT, 2_430_000),
]

TEST_KEYS = {A.TEST, A.TEST_SPEC, A.TEST_DESCENDING}

LOCALIZATIONS = {
    'en': AchievementsEnglishLocalization(),
    'ru': AchievementsRussianLocalization(),
}


def demo_achievement(key, value, spec, i) -> Achievement:
    scale = ACHIEVEMENT_DESC_MAP[key].milestone_scale
    ts = DEMO_TS
    previous_ts = ts - (7 + i * 13 % 120) * DAY
    if key == A.COIN_MARKET_CAP_RANK:
        # the rank goes down: the "milestone" is the new rank itself
        return Achievement(key, value, value, ts, value + 3, previous_ts, spec, descending=True)
    milestone = scale.previous(value)
    prev_milestone = scale.previous(milestone - 1) if milestone > 1 else 0
    return Achievement(key, value, milestone, ts, prev_milestone, previous_ts, spec)


def demo_entries():
    entries = list(DEMO_VALUES)
    listed = {key for key, _ in entries}
    for key in ACHIEVEMENT_DESC_MAP:
        if key not in listed and key not in TEST_KEYS:
            print(f'No demo value for {key!r}, using {DEFAULT_VALUE}: add it to DEMO_VALUES')
            entries.append((key, DEFAULT_VALUE))
    return entries


def main():
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR)

    count = 0
    for i, (key, v) in enumerate(demo_entries()):
        value, spec = v if isinstance(v, tuple) else (v, '')
        ach = demo_achievement(key, value, spec, i)
        for lang, loc in LOCALIZATIONS.items():
            parameters = build_achievement_card(ach, loc)
            spec_suffix = f'_{spec.split(".")[1].split("-")[0].lower()}' if spec else ''
            name = f'ach_{key}{spec_suffix}_{lang}'
            demo = {
                'template_name': ACHIEVEMENT_TEMPLATE,
                'meta': {
                    'title': parameters['title'],
                    'subtitle': parameters['number_text'],
                    'lang': lang,
                    'order': i,
                },
                'parameters': parameters,
            }
            with open(os.path.join(OUT_DIR, f'{name}.json'), 'w') as f:
                json.dump(demo, f, indent=2, ensure_ascii=False)
                f.write('\n')
            count += 1

    print(f'Wrote {count} achievement demos to {os.path.abspath(OUT_DIR)}')


if __name__ == '__main__':
    main()
