import json
import os
from typing import NamedTuple

from comm.localization.achievements.common import AchievementsLocalizationBase
from jobs.achievement.ach_list import Achievement, A, NUMBER_FONT_BALLOON, BG_LIQUIDITY
from lib.date_utils import today_str, now_ts
from models.asset import Asset

ACHIEVEMENT_TEMPLATE = 'achievement.jinja2'


class WreathStyle(NamedTuple):
    tint: str  # glow color
    # the hole inside the wreath as fractions of the background size: the number is fitted into this circle
    hole_x: float
    hole_y: float
    hole_r: float
    # the color at the picture edges: the card takes it, so the picture flows into the card without a seam
    base: str = '#0a1015'
    # where the background sits on the card, px; a frame with something hanging under the ring
    # goes smaller and higher, so it stays above the title
    size: int = 860
    top: int = 40
    shade_from: int = 58  # % of the card height where the shade under the title starts


# The style of every frame, keyed by its picture (the BG_* constants). The frame tuner of the renderer gallery
# (/render/frames) writes this file: the hole starts from an automatic guess and is set by eye; docs/achievement-frames.md
FRAME_STYLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'renderer',
                                'achievement_frames.json')


def load_frame_styles(path=FRAME_STYLE_FILE) -> dict:
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    # "note" is for people: why the hole sits where it does
    return {bg: WreathStyle(**{k: v for k, v in style.items() if k in WreathStyle._fields})
            for bg, style in raw.items()}


BACKGROUND_STYLE = load_frame_styles()

# the anniversary digits are pictures: data/renderer/static/img/achievement/balloon/; other numbers are text
BALLOON_GLYPHS = {c: f'{c}.png' for c in '0123456789'}


def number_glyphs(text: str, font: str) -> list:
    if font != NUMBER_FONT_BALLOON:
        return []
    return [{'kind': 'glyph', 'src': f'{font}/{BALLOON_GLYPHS[ch]}'} for ch in text if ch in BALLOON_GLYPHS]


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
        'base_color': style.base,
        'frame_size': style.size,
        'frame_top': style.top,
        'shade_from': style.shade_from,
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
