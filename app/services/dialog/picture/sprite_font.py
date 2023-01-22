import os

from PIL import Image

from services.lib.draw_utils import paste_image_masked
from services.lib.money import RAIDO_GLYPH


class SpriteFont:
    DEFAULT_AVAILABLE_SYMBOLS = f'1234567890ABCDEGKLMNTHROVX${RAIDO_GLYPH} '
    DEFAULT_SPECIAL_NAMES = {
        '$': 'USD',
        RAIDO_GLYPH: 'R',
    }

    def __init__(self, path, spacing=4, borders=4, whitespace_width=40,
                 available_symbols=DEFAULT_AVAILABLE_SYMBOLS, symbols_special_names=None):
        self.path = path
        self.spacing = spacing
        self.borders = borders
        self.available_symbols = available_symbols
        self.symbol_special_names = symbols_special_names or self.DEFAULT_SPECIAL_NAMES
        self.whitespace_width = whitespace_width
        self.symbols = {s: self._symbol_to_image(s) for s in self.available_symbols}

    def _symbol_to_image(self, symbol: str) -> Image:
        if symbol == ' ':
            return Image.new(mode='RGBA', size=(self.whitespace_width, 1), color=(0, 0, 0, 0))
        symbol = self.symbol_special_names.get(symbol, symbol)
        # noinspection PyTypeChecker
        return Image.open(os.path.join(self.path, f'{symbol}.png'))

    def render_string(self, string):
        for s in string:
            if s not in self.symbols:
                raise ValueError(f'Unknown symbol "{s}" in the string "{string}"!')

        images = [self.symbols.get(s) for s in string]
        if not images:
            return None
        max_height = max(i.height for i in images)
        width = sum(i.width for i in images) + self.spacing * (len(images) - 1) + self.borders * 2
        height = max_height + self.borders * 2
        canvas = Image.new(mode='RGBA', size=(width, height), color=(0, 0, 0, 0))
        base_line = height // 2

        x = self.borders
        for image in images:
            paste_image_masked(canvas, image, (int(x), int(base_line)), 'lm')
            x += self.spacing + image.width

        return canvas
