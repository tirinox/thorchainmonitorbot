"""
Tools for the achievement card frames (backgrounds), see docs/achievement-frames.md.
Run from app/:  PYTHONPATH=. python tools/achievement_frame.py <command> ...

  generate  draw frame candidates with an image model on OpenRouter (key: OPENROUTER_API_KEY, env or ../.env)
  measure   find the hole of a frame, its edge (base) color and how far the ornament reaches
  preview   render a real achievement card on a candidate frame through the running renderer (make renderer-dev)
"""
import argparse
import base64
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BG_DIR = 'data/renderer/static/img/achievement/bg'
DEFAULT_MODEL = 'google/gemini-3-pro-image'
DEFAULT_RENDERER = 'http://127.0.0.1:8404/render'
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'


# ---- generate ----

def _openrouter_key():
    key = os.environ.get('OPENROUTER_API_KEY')
    if not key:
        from dotenv import load_dotenv
        load_dotenv('../.env')
        key = os.environ.get('OPENROUTER_API_KEY')
    if not key:
        sys.exit('OPENROUTER_API_KEY is not set (env or ../.env)')
    return key


def _data_url(path):
    return 'data:image/png;base64,' + base64.b64encode(open(path, 'rb').read()).decode()


def generate_one(key, model, prompt, refs, seed, out_path):
    content = [{'type': 'text', 'text': prompt}]
    for ref in refs:
        content.append({'type': 'image_url', 'image_url': {'url': _data_url(ref)}})
    body = {
        'model': model,
        'messages': [{'role': 'user', 'content': content}],
        'modalities': ['image', 'text'],
        'image_config': {'aspect_ratio': '1:1'},
        'seed': seed,  # Gemini ignores the reasoning effort: only the seed changes the picture
        'usage': {'include': True},
    }
    req = urllib.request.Request(OPENROUTER_URL, data=json.dumps(body).encode(),
                                 headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=400).read())
    except urllib.error.HTTPError as e:
        print(f'seed {seed}: HTTP {e.code} {e.read().decode()[:300]}')
        return
    images = resp['choices'][0]['message'].get('images') or []
    if not images:
        print(f'seed {seed}: no image in the answer')
        return
    raw = base64.b64decode(images[0]['image_url']['url'].split(',', 1)[1])
    Image.open(io.BytesIO(raw)).convert('RGB').save(out_path, optimize=True)
    cost = resp.get('usage', {}).get('cost')
    print(f'seed {seed}: {out_path}  cost ${cost}  {time.time() - t0:.0f}s')


def cmd_generate(args):
    key = _openrouter_key()
    prompt = open(args.prompt).read()
    refs = [r if os.path.exists(r) else os.path.join(BG_DIR, r) for r in args.ref]
    os.makedirs(args.out, exist_ok=True)
    for seed in args.seeds:
        generate_one(key, args.model, prompt, refs, seed, os.path.join(args.out, f'{args.name}_s{seed}.png'))


# ---- measure ----

def _fit_circle(pts):
    x, y = pts[:, 0], pts[:, 1]
    c, *_ = np.linalg.lstsq(np.c_[2 * x, 2 * y, np.ones(len(x))], x ** 2 + y ** 2, rcond=None)
    return c[0], c[1], np.sqrt(c[2] + c[0] ** 2 + c[1] ** 2)


MIN_HOLE_POINTS = 20  # of the 180 rays: fewer stops do not make a circle


def find_hole(path, brighter_by=30, start=(0.5, 0.47)):
    """
    Rays from the middle stop where the picture gets brighter than the middle by `brighter_by`;
    a circle is fitted to the stops, outliers dropped. Returns (x, y, r) as fractions of the picture size,
    or None when there is no hole at this threshold: too few rays stop (the middle is as bright as the ornament,
    or the fit drifted out of the opening onto it).
    """
    lum = np.asarray(Image.open(path).convert('L').filter(ImageFilter.GaussianBlur(4)), dtype=float)
    h, w = lum.shape
    x0, y0 = w * start[0], h * start[1]
    r = 0
    for _ in range(4):
        if not (30 <= x0 < w - 30 and 30 <= y0 < h - 30):
            return None
        thr = np.median(lum[int(y0) - 30:int(y0) + 30, int(x0) - 30:int(x0) + 30]) + brighter_by
        pts = []
        for ang in np.linspace(0, 2 * np.pi, 180, endpoint=False):
            for dist in range(10, int(w * 0.44)):
                x, y = int(x0 + np.cos(ang) * dist), int(y0 + np.sin(ang) * dist)
                if not (0 <= x < w and 0 <= y < h):
                    break
                if lum[y, x] > thr:
                    pts.append((x, y))
                    break
        if len(pts) < MIN_HOLE_POINTS:
            return None
        pts = np.array(pts, float)
        x0, y0, r = _fit_circle(pts)
        for _ in range(3):
            d = np.hypot(pts[:, 0] - x0, pts[:, 1] - y0) - r
            keep = np.abs(d) < 2.5 * np.median(np.abs(d)) + 4
            if keep.sum() < MIN_HOLE_POINTS:
                break
            x0, y0, r = _fit_circle(pts[keep])
    return x0 / w, y0 / h, r / w


def edge_color(path, border=24):
    """Median color of the picture border: WreathStyle.base, the card takes it (tests check it)"""
    a = np.asarray(Image.open(path).convert('RGB'), dtype=float)
    b = border
    ring = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    return '#%02x%02x%02x' % tuple(np.median(ring, 0).astype(int))


def ornament_rows(path, brightness=50):
    lum = np.asarray(Image.open(path).convert('L'), dtype=float)
    rows = np.where((lum > brightness).sum(1) > 3)[0]
    return rows.min() / lum.shape[0], rows.max() / lum.shape[0]


def cmd_measure(args):
    for path in args.images:
        print(path)
        print(f'  base (edge color): {edge_color(path)}')
        top, bottom = ornament_rows(path)
        print(f'  ornament from {top:.3f} to {bottom:.3f} of the height')
        circles = []
        for brighter_by, color in ((15, 'red'), (30, 'lime'), (50, 'magenta')):
            hole = find_hole(path, brighter_by)
            if hole is None:
                print(f'  hole at +{brighter_by}: not found')
                continue
            x, y, r = hole
            circles.append((x, y, r, color))
            print(f'  hole at +{brighter_by}: x={x:.3f} y={y:.3f} r={r:.3f}')
        if args.overlay:
            im = Image.open(path).convert('RGB')
            d = ImageDraw.Draw(im)
            w = im.width
            for x, y, r, color in circles:
                x, y, r = x * w, y * w, r * w
                d.ellipse((x - r, y - r, x + r, y + r), outline=color, width=3)
                d.line((x - 15, y, x + 15, y), fill=color, width=3)
                d.line((x, y - 15, x, y + 15), fill=color, width=3)
            os.makedirs(args.overlay, exist_ok=True)
            out = os.path.join(args.overlay, 'holes_' + os.path.basename(path))
            im.save(out)
            print(f'  overlay: {out} (red +15, green +30, magenta +50)')


# ---- preview ----

def cmd_preview(args):
    from comm.localization.achievements.ach_eng import AchievementsEnglishLocalization
    from comm.localization.achievements.ach_rus import AchievementsRussianLocalization
    from comm.picture.achievement_card import build_achievement_card, ACHIEVEMENT_TEMPLATE
    from jobs.achievement.ach_list import Achievement

    loc = AchievementsRussianLocalization() if args.lang == 'ru' else AchievementsEnglishLocalization()
    ts = time.time()
    value, milestone, previous = args.values
    a = Achievement(args.key, value, milestone, ts, previous, ts - 40 * 86400)
    os.makedirs(args.out, exist_ok=True)

    for path in args.images:
        hole = args.hole or find_hole(path)
        if hole is None:
            sys.exit(f'{path}: no hole found at +30, pass it with --hole X Y R')
        tmp = f'zz_preview_{os.path.basename(path)}'  # the renderer serves only its static dir
        shutil.copy(path, os.path.join(BG_DIR, tmp))
        try:
            p = build_achievement_card(a, loc)
            p.update(background=tmp, hole_x=hole[0], hole_y=hole[1], hole_r=hole[2],
                     base_color=edge_color(path), frame_size=args.size, frame_top=args.top, shade_from=args.shade)
            if args.tint:
                p['tint'] = args.tint
            req = urllib.request.Request(args.renderer,
                                         data=json.dumps({'template_name': ACHIEVEMENT_TEMPLATE, 'parameters': p}).encode(),
                                         headers={'Content-Type': 'application/json'})
            out = os.path.join(args.out, 'card_' + os.path.basename(path))
            with open(out, 'wb') as f:
                f.write(urllib.request.urlopen(req, timeout=60).read())
            print(f'{out}  hole {hole[0]:.3f} {hole[1]:.3f} {hole[2]:.3f}')
        finally:
            os.remove(os.path.join(BG_DIR, tmp))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    g = sub.add_parser('generate', help='draw frame candidates')
    g.add_argument('--prompt', required=True, help='a text file with the prompt')
    g.add_argument('--name', required=True, help='file name prefix of the candidates')
    g.add_argument('--out', default='../temp/frames')
    g.add_argument('--seeds', type=int, nargs='+', default=[1, 2, 3])
    g.add_argument('--ref', nargs='*', default=[], help='reference pictures: a path or a file name in the bg dir')
    g.add_argument('--model', default=DEFAULT_MODEL)
    g.set_defaults(func=cmd_generate)

    m = sub.add_parser('measure', help='hole, base color and ornament extent of pictures')
    m.add_argument('images', nargs='+')
    m.add_argument('--overlay', help='a dir to save the pictures with the hole circles drawn on them')
    m.set_defaults(func=cmd_measure)

    p = sub.add_parser('preview', help='render a real card on candidate pictures')
    p.add_argument('images', nargs='+')
    p.add_argument('--key', required=True, help='achievement key, e.g. tvl, wallet_count')
    p.add_argument('--values', type=float, nargs=3, default=[52_400_000, 50_000_000, 20_000_000],
                   metavar=('VALUE', 'MILESTONE', 'PREVIOUS'))
    p.add_argument('--lang', choices=['en', 'ru'], default='en')
    p.add_argument('--tint')
    p.add_argument('--hole', type=float, nargs=3, metavar=('X', 'Y', 'R'), help='default: measured at +30')
    p.add_argument('--size', type=int, default=860)
    p.add_argument('--top', type=int, default=40)
    p.add_argument('--shade', type=int, default=58)
    p.add_argument('--renderer', default=DEFAULT_RENDERER)
    p.add_argument('--out', default='../temp/frames')
    p.set_defaults(func=cmd_preview)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
