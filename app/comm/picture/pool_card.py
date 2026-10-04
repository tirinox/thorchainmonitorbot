import re
from typing import Optional

from comm.localization.eng_base import BaseLocalization
from lib.date_utils import today_str
from lib.money import short_dollar, pretty_dollar
from models.asset import Asset
from models.pool_info import PoolInfoMap

POOL_ACTIVATED_TEMPLATE = 'pool_activated.jinja2'


def pool_activated_card_filename(pool_name: str):
    name = re.sub(r'[^A-Za-z0-9]+', '-', Asset.from_string(pool_name).name).strip('-') or 'pool'
    return f'THORChain-pool-{name}-{today_str()}.png'


def short_contract(tag: str, begin=6, end=4):
    """The contract of a token as it is told apart from the same token on another chain: 0x8AC7…580D"""
    if tag[:2] == '0X':  # the asset is upper-cased as a whole, the prefix of an address is not
        tag = '0x' + tag[2:]
    return f'{tag[:begin]}…{tag[-end:]}' if len(tag) > begin + end else tag


def build_pool_activated_card(pool_name: str, pool_info_map: Optional[PoolInfoMap], usd_per_rune: float,
                              loc: BaseLocalization, chain_logo='', trading_paused: Optional[bool] = None) -> dict:
    """
    Parameters for the pool_activated.jinja2 template; all texts come localized.
    The numbers that are not known (the pool is not in the map, no RUNE price) are left out.
    A pool opens before the trading of a new chain does, so the card tells whether the trading through the chain
    is on (trading_paused False) or paused (True); None, when the bot does not know the chain, tells nothing.
    """
    asset = Asset.from_string(pool_name).l1_asset
    pool = (pool_info_map or {}).get(pool_name)

    stats = []
    if pool and usd_per_rune:
        stats.append({'label': loc.TEXT_PIC_POOL_DEPTH, 'value': short_dollar(pool.usd_depth(usd_per_rune))})
        if pool.balance_asset:
            stats.append({'label': loc.TEXT_PIC_POOL_PRICE,
                          'value': pretty_dollar(pool.runes_per_asset * usd_per_rune)})
    if pool_info_map:
        stats.append({'label': loc.TEXT_PIC_POOL_ACTIVE_COUNT,
                      'value': str(sum(1 for p in pool_info_map.values() if p.is_enabled))})

    return {
        'pool': pool_name,
        'ticker': asset.name,
        'pool_label': asset.pretty_str,
        'contract': short_contract(asset.tag),
        'asset_logo': str(asset),
        'chain_logo': chain_logo,
        'stats': stats,
        'trading': '' if trading_paused is None else ('paused' if trading_paused else 'on'),
        't': {
            'title': loc.TEXT_PIC_POOL_TITLE.upper(),
            'activated': loc.TEXT_PIC_POOL_ACTIVATED,
            'tagline': loc.TEXT_PIC_POOL_TAGLINE,
            'trading_on': loc.TEXT_PIC_POOL_TRADING_ON,
            'trading_paused': loc.TEXT_PIC_POOL_TRADING_PAUSED,
        },
    }
