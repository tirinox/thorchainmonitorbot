from typing import NamedTuple

from comm.localization.achievements.common import AchievementsLocalizationBase
from jobs.achievement.ach_list import Achievement, A, NUMBER_FONT_BALLOON, BG_LIQUIDITY, BG_NETWORK, BG_SWAPS, \
    BG_USERS, BG_RUNE, BG_REVENUE, BG_BURN, BG_VAULT, BG_BTC, BG_ETH, BG_ANNIVERSARY
from lib.date_utils import today_str, now_ts
from lib.money import RAIDO_GLYPH
from models.asset import Asset

ACHIEVEMENT_TEMPLATE = 'achievement.jinja2'


class WreathStyle(NamedTuple):
    tint: str  # glow color
    # the hole inside the wreath as fractions of the background size: the number is fitted into this circle
    hole_x: float
    hole_y: float
    hole_r: float
    # 'round': a soft round fade around the hole; 'edges': only the picture edges fade,
    # for a background whose ornament spreads far from the ring
    mask: str = 'round'


# Holes were measured on the pictures: rays cast from the middle stop where it gets brighter than the middle
# by 30, a circle is fitted to the stops
BACKGROUND_STYLE = {
    BG_LIQUIDITY: WreathStyle('#3ee6c8', 0.501, 0.463, 0.165),
    BG_NETWORK: WreathStyle('#6fe8cf', 0.500, 0.469, 0.173),
    BG_SWAPS: WreathStyle('#4ffffa', 0.503, 0.448, 0.202),
    BG_USERS: WreathStyle('#7cc7ff', 0.492, 0.466, 0.210),  # dark twigs fool the rays: radius set by eye
    BG_RUNE: WreathStyle('#2ee6b8', 0.499, 0.496, 0.190),
    BG_REVENUE: WreathStyle('#e8c45a', 0.499, 0.445, 0.216),
    BG_BURN: WreathStyle('#ffb347', 0.487, 0.456, 0.162),
    BG_VAULT: WreathStyle('#ffcf7a', 0.511, 0.436, 0.188),
    BG_BTC: WreathStyle('#ffb84d', 0.499, 0.494, 0.189),
    BG_ETH: WreathStyle('#b4a6ff', 0.500, 0.495, 0.188),
    BG_ANNIVERSARY: WreathStyle('#f4e18d', 0.499, 0.495, 0.187, mask='edges'),
}

# sprite fonts in data/renderer/static/img/achievement/<font>/
RUNIC_GLYPHS = {
    **{c: f'bw_{c}.png' for c in '0123456789ABCDEGHKLMNORTVX'},
    '$': 'bw_USD.png',
    RAIDO_GLYPH: 'bw_R.png',
    '.': 'bw__.png',
}
BALLOON_GLYPHS = {c: f'{c}.png' for c in '0123456789'}


def number_glyphs(text: str, font: str) -> list:
    table = BALLOON_GLYPHS if font == NUMBER_FONT_BALLOON else RUNIC_GLYPHS
    glyphs = []
    for ch in text:
        if ch == ' ':
            glyphs.append({'kind': 'space'})
        elif file := table.get(ch.upper()):
            kind = {'.': 'dot', '$': 'tall'}.get(ch, 'glyph')
            glyphs.append({'kind': kind, 'src': f'{font}/{file}'})
        else:
            # no sprite for it (e.g. "-"): the regular font draws it
            glyphs.append({'kind': 'text', 'text': ch})
    return glyphs


def _stat(label, value, sub=''):
    return {'label': label, 'value': value, 'sub': sub}


def build_achievement_card(a: Achievement, loc: AchievementsLocalizationBase) -> dict:
    """Parameters for the achievement.jinja2 template; all texts come localized"""
    desc, ago, desc_text, _, milestone_str, _, _ = loc.prepare_achievement_data(a)

    style = BACKGROUND_STYLE.get(desc.background, BACKGROUND_STYLE[BG_LIQUIDITY])

    is_rank = a.key == A.COIN_MARKET_CAP_RANK
    is_anniversary = a.key == A.ANNIVERSARY

    if is_rank:
        number_label = loc.CARD_RANK_LABEL
    elif desc.more_than:
        number_label = loc.LESS_THAN if a.descending else loc.MORE_THAN
    else:
        number_label = ''

    def fmt(v):
        return f'#{int(v)}' if is_rank else loc.format_value(v, a, desc)

    stats = []
    if not is_anniversary:
        if a.has_previous:
            stats.append(_stat(loc.CARD_PREVIOUS, fmt(a.prev_milestone), loc.card_ago(ago) if ago else ''))
        if not a.descending and int(a.value) != int(a.milestone):
            stats.append(_stat(loc.CARD_NOW, loc.format_value(a.value, a, desc, short=False)))
        if (next_milestone := a.get_next_milestone()) > 0:
            stats.append(_stat(loc.CARD_NEXT, fmt(next_milestone)))

    asset_logo = str(Asset.from_string(a.specialization).l1_asset) if a.specialization else ''

    return {
        'key': a.key,
        'background': desc.background,
        'tint': desc.tint or style.tint,
        'hole_x': style.hole_x,
        'hole_y': style.hole_y,
        'hole_r': style.hole_r,
        'mask': style.mask,
        'number_font': desc.number_font,
        'number_label': number_label,
        'number_text': milestone_str,
        'glyphs': number_glyphs(milestone_str, desc.number_font),
        'title': desc_text,
        'subtitle': loc.card_anniversary_subtitle(int(a.milestone)) if is_anniversary else '',
        'asset_logo': asset_logo,
        'date': loc.format_date(a.timestamp or now_ts()),
        'stats': stats,
    }


def achievement_card_filename(a: Achievement):
    return f'thorchain-ach-{a.key}-{today_str()}.png'
