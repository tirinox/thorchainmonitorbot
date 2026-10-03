"""
Makes the land mask of the world for the dotted maps of the node infographic (nodes.jinja2):
data/renderer/static/js/world_land.js, a bit per cell of an equirectangular grid, from 180°W 90°N.
The land is read from the old map picture data/earth-bg.png: dark land on a blue ocean.

Usage (from app/):  PYTHONPATH=. python tools/world_land_mask.py [--cell 0.5] [--show]
"""
import argparse
import base64
import os

from PIL import Image

from lib.path import get_data_path

SOURCE = os.path.join(get_data_path(), 'earth-bg.png')
TARGET = os.path.join(get_data_path(), 'renderer', 'static', 'js', 'world_land.js')

LAND_SHARE = 0.5  # a cell is land when at least this part of it is
MAX_LAT = 83.5  # the picture is dark above it: its frame, not land


def is_land(pixel) -> bool:
    # the land is (18, 25, 32), the ocean has no red and a lot of blue
    r, g, b = pixel[:3]
    return r > 9 and b < 50


def build_mask(cell_deg: float):
    im = Image.open(SOURCE).convert('RGB')
    src_w, src_h = im.size
    px = im.load()

    w, h = round(360 / cell_deg), round(180 / cell_deg)
    rows = []
    for j in range(h):
        y0, y1 = int(j * src_h / h), max(int((j + 1) * src_h / h), int(j * src_h / h) + 1)
        if 90 - (j + 0.5) * cell_deg > MAX_LAT:
            rows.append([False] * w)
            continue
        row = []
        for i in range(w):
            x0, x1 = int(i * src_w / w), max(int((i + 1) * src_w / w), int(i * src_w / w) + 1)
            cells = [is_land(px[x, y]) for y in range(y0, y1) for x in range(x0, x1)]
            row.append(sum(cells) >= LAND_SHARE * len(cells))
        rows.append(row)
    return w, h, rows


def pack_bits(rows) -> str:
    bits = [b for row in rows for b in row]
    data = bytearray((len(bits) + 7) // 8)
    for n, bit in enumerate(bits):
        if bit:
            data[n >> 3] |= 0x80 >> (n & 7)
    return base64.b64encode(bytes(data)).decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cell', type=float, default=0.5, help='size of a cell in degrees')
    parser.add_argument('--show', action='store_true', help='print the mask to the terminal, every 4th cell')
    args = parser.parse_args()

    w, h, rows = build_mask(args.cell)
    if args.show:
        for row in rows[::8]:
            print(''.join('#' if b else ' ' for b in row[::4]))

    with open(TARGET, 'w') as f:
        f.write('// The land of the world for the dotted maps: an equirectangular grid of w x h cells from 180°W 90°N,\n'
                '// row by row, a bit per cell (the high bit first), base64. Made by tools/world_land_mask.py\n')
        f.write(f"const WORLD_LAND = {{w: {w}, h: {h}, bits: '{pack_bits(rows)}'}};\n")

    land = sum(sum(row) for row in rows)
    print(f'{TARGET}: {w} x {h} cells, {land / (w * h):.1%} land, {os.path.getsize(TARGET)} bytes')


if __name__ == '__main__':
    main()
