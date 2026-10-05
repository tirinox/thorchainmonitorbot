import json

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from comm.picture.crypto_logo import chain_logo_name
from comm.picture.lp_card import build_lp_add_card, LP_ADD_TEMPLATE
from lib.config import Config
from models.asset import Asset
from models.memo import ActionType
from models.pool_info import PoolInfo
from models.tx import ThorAction, EventLargeTransaction, ThorSubTx, ThorCoin


def make_lp_add_event(pool, rune_amount, asset_amount, asset_price_usd, depth_usd, usd_per_rune=0.8,
                      sender='thor1qx9fz0m4k0lpy8zqhd7c0u0c6w5cd3x9f2') -> EventLargeTransaction:
    """A synthetic add of liquidity, as Midgard gives it: one inbound per side; depth_usd is the pool after it"""
    balance_rune = depth_usd / 2 / usd_per_rune
    balance_asset = balance_rune * usd_per_rune / asset_price_usd
    in_tx = []
    if rune_amount:
        in_tx.append(ThorSubTx(sender, [ThorCoin(int(rune_amount * 1e8), 'THOR.RUNE')], 'RUNEHASH'))
    if asset_amount:
        in_tx.append(ThorSubTx(sender, [ThorCoin(int(asset_amount * 1e8), pool)], 'ASSETHASH'))
    tx = ThorAction(date_timestamp=0, height=0, status='success', type=ActionType.ADD_LIQUIDITY.value,
                    pools=[pool], in_tx=in_tx, out_tx=[])
    tx.asset_per_rune = balance_asset / balance_rune
    tx.full_volume_in_rune = tx.rune_amount + tx.asset_amount / tx.asset_per_rune
    pool_info = PoolInfo(pool, int(balance_asset * 1e8), int(balance_rune * 1e8), 1, PoolInfo.AVAILABLE)
    return EventLargeTransaction(tx, usd_per_rune, pool_info)


USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'

DEMOS = (
    # name, localization, the event, title
    ('lp_add_sym', EnglishLocalization, ('BTC.BTC', 38_000, 0.41, 73_400, 45_000_000),
     'Liquidity added: symmetric, a drop in a deep pool'),
    ('lp_add_asym_ru', RussianLocalization, (USDC, 0, 120_000, 1.0, 8_100_000),
     'Liquidity added: single-sided USDC, in Russian'),
    ('lp_add_mega', EnglishLocalization, ('ZEC.ZEC', 32_000, 18.0, 1_411, 52_100),
     'Liquidity added: bigger than the whole pool was (the pool grew x43)'),
    ('lp_add_mega_ru', RussianLocalization, ('ZEC.ZEC', 0, 36.0, 1_411, 52_100),
     'Liquidity added: a single-sided record, in Russian'),
)


def save_gallery_demos():
    """Writes renderer/demo/lp_add_*.json; the gallery is at http://127.0.0.1:8404/render/demo"""
    cfg = Config()
    for order, (name, loc_class, args, title) in enumerate(DEMOS):
        loc = loc_class(cfg)
        event = make_lp_add_event(*args)
        asset = Asset.from_string(event.transaction.first_pool)
        parameters = build_lp_add_card(event, loc, 'thor1qx...x9f2', chain_logo_name(asset))
        demo = {'template_name': LP_ADD_TEMPLATE, 'parameters': parameters,
                'meta': {'title': title, 'lang': 'ru' if name.endswith('_ru') else 'en', 'order': order}}
        with open(f'renderer/demo/{name}.json', 'w', encoding='utf-8') as f:
            json.dump(demo, f, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    save_gallery_demos()
