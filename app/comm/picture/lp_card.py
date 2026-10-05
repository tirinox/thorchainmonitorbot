from comm.localization.eng_base import BaseLocalization
from lib.date_utils import today_str
from models.asset import Asset
from models.tx import EventLargeTransaction

LP_ADD_TEMPLATE = 'lp_add.jinja2'

# % of the pool depth after the add: above it the add is bigger than the whole pool was, and the card celebrates
MEGA_SHARE = 50.0


def lp_add_card_filename(pool_name: str):
    return f'THORChain-liquidity-{Asset.from_string(pool_name).name}-{today_str()}.png'


def build_lp_add_card(e: EventLargeTransaction, loc: BaseLocalization, user_name='', chain_logo='') -> dict:
    """
    Parameters for the lp_add.jinja2 template; all texts come localized.
    The pool depth is the one after the add, as in the text: before = now - added.
    """
    tx = e.transaction
    asset = Asset.from_string(tx.first_pool).l1_asset
    usd_per_rune = e.usd_per_rune or 0.0

    total_usd = tx.full_volume_in_rune * usd_per_rune
    rune_usd = tx.rune_amount * usd_per_rune
    asset_usd = max(total_usd - rune_usd, 0.0)

    depth_usd = e.pool_info.usd_depth(usd_per_rune) if e.pool_info else 0.0
    share = min(tx.what_percent_of_pool(e.pool_info), 100.0) if depth_usd else 0.0
    before_usd = max(depth_usd - total_usd, 0.0)
    mega = bool(depth_usd) and share > MEGA_SHARE
    multiplier = round(depth_usd / before_usd) if mega and before_usd > 0 else 0

    has_rune, has_asset = tx.rune_amount > 0, tx.asset_amount > 0
    if mega and multiplier:
        badge = f'{loc.TEXT_PIC_LP_POOL_WORD.upper()} ×{multiplier}'
    else:
        badge = loc.TEXT_PIC_LP_SYMMETRIC if has_rune and has_asset else loc.TEXT_PIC_LP_SINGLE_SIDED

    return {
        'pool': tx.first_pool,
        'ticker': asset.name,
        'asset_logo': str(asset),
        'chain_logo': chain_logo,
        'rune_amount': tx.rune_amount,
        'asset_amount': tx.asset_amount,
        'rune_usd': rune_usd,
        'asset_usd': asset_usd,
        'total_usd': total_usd,
        'depth_usd': depth_usd,
        'before_usd': before_usd,
        'share': share,
        'mega': mega,
        'multiplier': multiplier,
        'user_name': user_name,
        't': {
            'title': loc.TEXT_PIC_LP_ADD_TITLE.upper(),
            'badge': badge,
            'added': loc.TEXT_PIC_LP_ADDED,
            'pool_grew': loc.TEXT_PIC_LP_POOL_GREW,
            'pool_filled': loc.TEXT_PIC_LP_POOL_FILLED,
            'pool': loc.text_pic_lp_pool(asset.name),
            'of_pool': loc.TEXT_PIC_LP_OF_POOL,
            'depth_now': loc.TEXT_PIC_LP_DEPTH_NOW,
            'no_rune': loc.text_pic_lp_no_side('RUNE'),
            'no_asset': loc.text_pic_lp_no_side(asset.name),
        },
    }
