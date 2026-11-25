# Renders the swap tracker promo (1920x1080, 30 fps): real Telegram screenshots of the bot's messages, cut into
# bubbles, arrive one by one in a Telegram window on the right; captions on the left. Frames are piped to ffmpeg.
# Also writes <out>.events.json: when each message arrives and its kind, for the sound effects.
# Usage: python render_chat.py <screenshots dir> <out.mp4>
# The screenshots are 1.webp 2.webp 3.png 4.webp 5.webp (crops below are pixel boxes in them).
import json
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SRC, OUT = sys.argv[1], sys.argv[2]
W, H, FPS = 1920, 1080, 30
BG = (17, 31, 40)  # Telegram night chat background
GAP = 10  # between messages
BUBBLE_X = 30
FONT = '/System/Library/Fonts/Avenir Next.ttc'  # 0 Bold, 2 Demi Bold, 5 Medium
LOGO = 'app/data/renderer/static/img/tc_logo_transparent.png'

# the chat is drawn at the screenshots' scale, then shrunk into the window on the right
CW, CH = 1062, 1250
SCALE = 0.8
PX, PY = 1010, 40
PW, PH = round(CW * SCALE), round(CH * SCALE)

_cache = {}


def shot(name):
    if name not in _cache:
        im = Image.open(f'{SRC}/{name}').convert('RGB')
        if name == '3.png':  # another theme: map its background and bubble colors onto the others
            a = np.asarray(im).astype(float)
            pts = [([0, 23, 38, 255], [0, 17, 25, 255]), ([0, 30, 50, 255], [0, 31, 51, 255]),
                   ([0, 38, 60, 255], [0, 40, 60, 255])]
            for c, (xp, fp) in enumerate(pts):
                a[..., c] = np.interp(a[..., c], xp, fp)
            im = Image.fromarray(a.astype('uint8'))
        if name == '5.webp':  # taken at a slightly smaller scale
            im = im.resize((round(im.width * 1.022), round(im.height * 1.022)), Image.LANCZOS)
        _cache[name] = im
    return _cache[name]


def crop(name, box):
    if name == '5.webp':
        box = tuple(round(v * 1.022) for v in box)
    return shot(name).crop(box)


def block(name, *boxes):
    """A message: its bubble and the inline buttons under it, stacked as in the screenshot (4 px apart)."""
    parts = [crop(name, b) for b in boxes]
    h = sum(p.height for p in parts) + 4 * (len(parts) - 1)
    out = Image.new('RGB', (max(p.width for p in parts), h), BG)
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height + 4
    return out


# --- captions (headline, subline) -----------------------------------------------------------------------------------
CAPTIONS = {
    'intro': ('Where is my swap?', 'THORChain Infobot follows every swap of your wallet'),
    'wallet': ('Add your wallet', 'Swap tracking is on by default, for any chain'),
    'detected': ('Spotted in seconds', 'Amount, route, expected output and time left'),
    'streaming': ('Streaming swaps, live', 'Progress sub-swap by sub-swap'),
    'sending': ('On its way', 'Outbound delays explained'),
    'delayed': ('Delayed? You’ll know why', 'Chain halts, paused trading, the outbound queue'),
    'burst': ('Dozens of swaps at once', 'Each one followed on its own'),
    'refund': ('Refunds, with the reason', None),
    'finished': ('The final report', 'Effective rate, every fee, and a card to share'),
    'outro': ('Track your swaps', 't.me/thor_infobot  ·  My wallets\nor just send the bot a tx hash'),
}

# (message, seconds until the next one, caption that starts with it, sound kind)
SCRIPT = [
    (block('1.webp', (46, 20, 964, 398), (46, 402, 964, 482), (46, 486, 964, 566)), 3.0, 'wallet', 'msg'),
    (block('1.webp', (46, 584, 976, 962), (46, 966, 976, 1046)), 2.6, 'detected', 'msg'),
    (block('1.webp', (46, 1064, 978, 1290)), 2.4, 'streaming', 'msg'),
    (block('1.webp', (46, 1294, 992, 1634)), 2.4, 'sending', 'msg'),
    (block('1.webp', (46, 1638, 992, 1864)), 3.2, 'delayed', 'warn'),
]
BURST = [
    block('5.webp', (57, 8, 982, 341)), block('5.webp', (57, 344, 969, 566)),
    block('5.webp', (57, 569, 968, 791)), block('5.webp', (57, 794, 966, 1127)),
    block('5.webp', (57, 1131, 968, 1352)), block('5.webp', (57, 1356, 982, 1689)),
    block('5.webp', (57, 1693, 968, 1914)),
    block('4.webp', (40, 670, 986, 1010)), block('4.webp', (40, 1014, 986, 1354)),
    block('4.webp', (40, 1358, 958, 1736), (40, 1740, 958, 1820)),
    block('3.png', (30, 18, 962, 244)), block('3.png', (30, 248, 976, 588)),
    block('3.png', (30, 592, 948, 932), (30, 936, 948, 1016)),
]
for i, b in enumerate(BURST):  # a wave of swaps: faster and faster
    SCRIPT.append((b, 0.6 - 0.3 * i / (len(BURST) - 1), 'burst' if i == 0 else None, 'msg'))
SCRIPT[-1] = (SCRIPT[-1][0], 1.2, None, 'msg')
SCRIPT += [
    (block('2.webp', (42, 118, 966, 410), (42, 414, 966, 494)), 3.0, 'refund', 'warn'),
    (block('2.webp', (42, 512, 960, 890), (42, 894, 960, 974)), 1.6, None, 'msg'),
    (block('2.webp', (42, 992, 988, 1884), (42, 1888, 988, 1968)), 3.6, 'finished', 'done'),
]
OUTRO, FADE = 4.5, 0.8

HEADER = shot('2.webp').crop((8, 0, 8 + CW, 112))
INPUT = shot('1.webp').crop((12, 1886, 12 + CW, 1988))
CHAT_BOTTOM = CH - INPUT.height - 16

START = 1.6  # the intro caption alone first
times, t = [], START
for item in SCRIPT:
    times.append(t)
    t += item[1]
OUTRO_T = t
TOTAL = t + OUTRO
heights = [s[0].height + GAP for s in SCRIPT]
tops = np.concatenate([[0], np.cumsum(heights)[:-1]])  # each message's top in the chat content

cap_times = [(0.0, 'intro')] + [(times[i], s[2]) for i, s in enumerate(SCRIPT) if s[2]] + [(OUTRO_T, 'outro')]


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def chat(t):
    img = Image.new('RGB', (CW, CH), BG)
    shown = [i for i, ti in enumerate(times) if ti <= t]
    prog = {i: ease((t - times[i]) / min(0.3, 0.8 * SCRIPT[i][1])) for i in shown}
    scroll = sum(prog[i] * heights[i] for i in shown)
    for i in reversed(shown):
        y = CHAT_BOTTOM + GAP - scroll + tops[i]
        b = SCRIPT[i][0]
        if y + b.height < 0:
            break
        alpha = min(1.0, prog[i] * 1.6)
        if alpha >= 1:
            img.paste(b, (BUBBLE_X, int(y)))
        else:
            bgp = img.crop((BUBBLE_X, int(y), BUBBLE_X + b.width, int(y) + b.height))
            img.paste(Image.blend(bgp, b, alpha), (BUBBLE_X, int(y)))
    img.paste(HEADER, (0, 0))
    img.paste(INPUT, (0, CH - INPUT.height))
    return img


# --- static layers ----------------------------------------------------------------------------------------------------
def background():
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    base = np.array([8, 18, 26], float) + np.array([6, 22, 26], float) * (xx / W)[..., None] * 0.6
    glow = np.exp(-(((xx - 1430) / 700) ** 2 + ((yy - 540) / 520) ** 2))[..., None]  # teal glow behind the window
    img = Image.fromarray(np.clip(base + glow * np.array([0, 60, 60]), 0, 255).astype('uint8'))
    shadow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((PX, PY + 14, PX + PW, PY + PH + 14), 26, fill=170)
    img.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(26)))
    logo = Image.open(LOGO).convert('RGBA')
    logo = logo.resize((round(logo.width * 64 / logo.height), 64), Image.LANCZOS)
    img.paste(logo, (110, 80), logo)
    ImageDraw.Draw(img).text((110 + logo.width + 20, 112), 'THORChain Infobot', font=ImageFont.truetype(FONT, 36, index=2),
                             fill=(235, 242, 245), anchor='lm')
    return img


BGIMG = background()
PANEL_MASK = Image.new('L', (PW, PH), 0)
ImageDraw.Draw(PANEL_MASK).rounded_rectangle((0, 0, PW - 1, PH - 1), 26, fill=255)

F_HEAD = ImageFont.truetype(FONT, 76, index=0)
F_SUB = ImageFont.truetype(FONT, 38, index=5)
TEXT_W = 820


def wrap(text, font):
    lines = []
    for para in text.split('\n'):
        line = ''
        for word in para.split(' '):
            cand = (line + ' ' + word).strip() if word else line + ' '
            if font.getlength(cand) <= TEXT_W or not line:
                line = cand
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def caption_image(key):
    head, sub = CAPTIONS[key]
    img = Image.new('RGBA', (TEXT_W + 40, 600), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 0
    for line in wrap(head, F_HEAD):
        d.text((0, y), line, font=F_HEAD, fill=(255, 255, 255))
        y += 92
    d.rounded_rectangle((2, y + 14, 92, y + 22), 4, fill=(51, 222, 200))  # accent bar
    y += 50
    for line in wrap(sub or '', F_SUB):
        d.text((0, y), line, font=F_SUB, fill=(160, 205, 212))
        y += 52
    return img.crop((0, 0, img.width, y + 10))


CAPS = {k: caption_image(k) for k in CAPTIONS}


def paste_caption(img, key, alpha, dy):
    c = CAPS[key]
    if alpha < 1:
        c = c.copy()
        c.putalpha(c.getchannel('A').point(lambda v: int(v * alpha)))
    img.paste(c, (110, int(540 - c.height / 2 + dy)), c)


def frame(t):
    img = BGIMG.copy()
    # the Telegram window slides in from the right at the start
    slide = ease((t - 0.2) / 0.7)
    img.paste(chat(t).resize((PW, PH), Image.LANCZOS), (int(PX + (1 - slide) * 960), PY), PANEL_MASK)
    # captions: the current one slides up and fades in while the previous one fades out
    k = max(i for i, (ts, _) in enumerate(cap_times) if ts <= t)
    ts, key = cap_times[k]
    p = ease((t - ts) / 0.5)
    if p < 1 and k > 0:
        paste_caption(img, cap_times[k - 1][1], 1 - p, -30 * p)
    paste_caption(img, key, p, 30 * (1 - p))
    if t > TOTAL - FADE:
        img = Image.blend(img, Image.new('RGB', (W, H)), (t - (TOTAL - FADE)) / FADE)
    return img


if __name__ == '__main__':
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                           '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
                           '-movflags', '+faststart', OUT], stdin=subprocess.PIPE)
    n = int(TOTAL * FPS)
    for k in range(n):
        ff.stdin.write(frame(k / FPS).tobytes())
    ff.stdin.close()
    ff.wait()
    events = [{'t': round(times[i], 3), 'kind': s[3]} for i, s in enumerate(SCRIPT)]
    json.dump({'duration': round(TOTAL, 3), 'events': events}, open(OUT + '.events.json', 'w'), indent=1)
    print(f'{OUT}: {n} frames, {TOTAL:.1f} s')
