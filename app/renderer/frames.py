"""
The achievement frames for the frame tuner of the gallery (/render/frames): the pictures, their styles and the demos
that show them. The styles live in data/renderer/achievement_frames.json, which the bot reads
(comm/picture/achievement_card.py). The tuner saves a frame there and into the achievement demos on that frame,
so the gallery shows it at once. The renderer has no bot dependencies, so all of it works on the JSON files.
"""
import json
import os
import re

from .demo import DEMO_DIR, demo_files

BG_DIR = 'data/renderer/static/img/achievement/bg'
BG_URL = '/static/img/achievement/bg'
STYLE_FILE = 'data/renderer/achievement_frames.json'
TUNER_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frame_tuner.html')
ACHIEVEMENT_TEMPLATE = 'achievement.jinja2'

# the fields of a style in the order the file keeps them; "note" says why the hole sits where it does
FIELDS = ('tint', 'hole_x', 'hole_y', 'hole_r', 'base', 'size', 'top', 'shade_from', 'note')
COLORS = ('tint', 'base')
# a number field => its lowest and highest value: the hole in fractions of the picture, the placement in card px
LIMITS = {
    'hole_x': (0.0, 1.0),
    'hole_y': (0.0, 1.0),
    'hole_r': (0.02, 0.5),
    'size': (300, 1024),
    'top': (-300, 600),
    'shade_from': (0, 100),
}
HOLE_DIGITS = 3  # 0.001 of the picture is about a pixel

# a style field => the achievement.jinja2 parameter it becomes, as build_achievement_card makes it
CARD_PARAMETERS = {
    'tint': 'tint',
    'hole_x': 'hole_x',
    'hole_y': 'hole_y',
    'hole_r': 'hole_r',
    'base': 'base_color',
    'size': 'frame_size',
    'top': 'frame_top',
    'shade_from': 'shade_from',
}

# a picture without a style starts with these (the WreathStyle defaults), the hole and the base are measured
NEW_STYLE = {'tint': '#ffcf7a', 'base': '#0a1015', 'size': 860, 'top': 40, 'shade_from': 58}

HEX_COLOR = re.compile(r'^#[0-9a-f]{6}$')


def frame_files(bg_dir=BG_DIR) -> list:
    return sorted(f for f in os.listdir(bg_dir) if f.endswith('.png'))


def load_styles(path=STYLE_FILE) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _write_json(path, data):
    # the whole text is made first, so a bad value can not leave half a file
    text = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def clean_style(raw: dict) -> dict:
    """A style from the tuner, checked and rounded as the file keeps it; a ValueError says what is wrong"""
    if not isinstance(raw, dict):
        raise ValueError('the style must be an object')
    style = {}
    for k in COLORS:
        v = str(raw.get(k, '')).strip().lower()
        if not HEX_COLOR.match(v):
            raise ValueError(f'{k} must be a color like #1a2b3c, not {raw.get(k)!r}')
        style[k] = v
    for k, (lo, hi) in LIMITS.items():
        try:
            v = float(raw[k])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f'{k} must be a number, not {raw.get(k)!r}')
        if not lo <= v <= hi:  # NaN fails it too
            raise ValueError(f'{k} = {v} is out of {lo}..{hi}')
        style[k] = round(v, HOLE_DIGITS) if k.startswith('hole_') else int(round(v))
    note = ' '.join(str(raw.get('note') or '').split())
    if note:
        style['note'] = note
    return {k: style[k] for k in FIELDS if k in style}


def patch_demos(frame: str, old: dict, style: dict, demo_dir=DEMO_DIR) -> list:
    """
    Puts the style into the achievement demos on this frame, as build_achievement_card would.
    An achievement may have a tint of its own: a demo keeps a tint that is not the old one of the frame.
    Returns the names of the demos that changed.
    """
    changed = []
    for name, path in sorted(demo_files(demo_dir).items()):
        with open(path, encoding='utf-8') as f:
            demo = json.load(f)
        p = demo.get('parameters') or {}
        if demo.get('template_name') != ACHIEVEMENT_TEMPLATE or p.get('background') != frame:
            continue
        before = dict(p)
        for field, param in CARD_PARAMETERS.items():
            if field == 'tint' and old and p.get('tint') != old.get('tint'):
                continue
            p[param] = style[field]
        if p != before:
            _write_json(path, demo)
            changed.append(name)
    return changed


def save_style(frame: str, raw: dict, style_path=STYLE_FILE, bg_dir=BG_DIR, demo_dir=DEMO_DIR):
    """Saves the style of a frame: a new frame goes to the end of the file. Returns the style and the patched demos"""
    if frame not in frame_files(bg_dir):
        raise ValueError(f'there is no frame picture {frame!r} in {bg_dir}')
    style = clean_style(raw)
    styles = load_styles(style_path)
    old = styles.get(frame)
    styles[frame] = style
    _write_json(style_path, styles)
    return style, patch_demos(frame, old, style, demo_dir)


def tuner_catalog(style_path=STYLE_FILE, bg_dir=BG_DIR, demo_dir=DEMO_DIR) -> dict:
    """What the tuner page starts with: the frames (new pictures first), their styles and the achievement demos"""
    styles = load_styles(style_path)
    demos = []
    for name, path in demo_files(demo_dir).items():
        with open(path, encoding='utf-8') as f:
            demo = json.load(f)
        if demo.get('template_name') != ACHIEVEMENT_TEMPLATE:
            continue
        meta = demo.get('meta') or {}
        demos.append({
            'name': name,
            'title': meta.get('title') or name,
            'lang': meta.get('lang') or ('ru' if name.endswith('_ru') else 'en'),
            'order': meta.get('order', 0),
            'frame': demo['parameters'].get('background', ''),
        })
    demos.sort(key=lambda d: (d['order'], d['name']))

    files = frame_files(bg_dir)
    order = [f for f in files if f not in styles] + [f for f in styles if f in files]
    frames = [{
        'file': f,
        'url': f'{BG_URL}/{f}',
        'style': styles.get(f),
        'users': [d['name'] for d in demos if d['frame'] == f],
    } for f in order]

    return {
        'frames': frames,
        'demos': demos,
        'fields': FIELDS,
        'limits': LIMITS,
        'card_parameters': CARD_PARAMETERS,
        'new_style': NEW_STYLE,
        'template': ACHIEVEMENT_TEMPLATE,
        'style_file': STYLE_FILE,
    }


def tuner_html() -> str:
    # "</" would close the <script> the JSON sits in
    payload = json.dumps(tuner_catalog(), ensure_ascii=False).replace('</', '<\\/')
    with open(TUNER_PAGE, encoding='utf-8') as f:
        return f.read().replace('__CATALOG__', payload)
