import math
from dataclasses import dataclass
from math import floor, log10
from typing import List

from services.lib.constants import Chains
from services.lib.utils import linear_transform

EMOJI_SCALE = [
    # negative
    (-50, '💥'), (-35, '👺'), (-25, '🥵'), (-20, '😱'), (-15, '😨'), (-10, '😰'), (-5, '😢'), (-3, '😥'), (-2, '😔'),
    (-1, '😑'), (0, '😕'),
    # positive
    (1, '😏'), (2, '😄'), (3, '😀'), (5, '🤗'), (10, '🍻'), (15, '🎉'), (20, '💸'), (25, '🔥'), (35, '🌙'), (50, '🌗'),
    (65, '🌕'), (80, '⭐'), (100, '✨'), (10000000, '🚀')
]

RAIDO_GLYPH = 'ᚱ'
ABSURDLY_LARGE_NUMBER = 1e+15


def emoji_for_percent_change(pc):
    for threshold, emoji in EMOJI_SCALE:
        if pc <= threshold:
            return emoji
    return EMOJI_SCALE[-1]  # last one


def number_commas(x):
    if not isinstance(x, int):
        raise TypeError("Parameter must be an integer.")
    if x < 0:
        return '-' + number_commas(-x)
    result = ''
    while x >= 1000:
        x, r = divmod(x, 1000)
        result = f",{r:03d}{result}"
    return f"{x:d}{result}"


def round_to_dig(x, e=2):
    return round(x, -int(floor(log10(abs(x)))) + e - 1)


def pretty_dollar(x, signed=False, postfix=''):
    return pretty_money(x, prefix='$', postfix=postfix, signed=signed)


def pretty_rune(x, signed=False, prefix=''):
    return pretty_money(x, postfix=RAIDO_GLYPH, signed=signed, prefix=prefix)


def pretty_money(x, prefix='', signed=False, postfix=''):
    if math.isnan(x):
        return str(x)
    if x < 0:
        return f"-{prefix}{pretty_money(-x)}{postfix}"
    elif x == 0:
        r = "0.0"
    else:
        if x < 1e-4:
            r = f'{x:.4f}'
        elif x < 100:
            r = str(round_to_dig(x, 3))
        elif x < 1000:
            r = str(round_to_dig(x, 4))
        else:
            x = int(round(x))
            r = number_commas(x)
    prefix = f'+{prefix}' if signed else prefix
    return f'{prefix}{r}{postfix}'


def too_big(x, limit_abs=1e7):
    return math.isinf(x) or math.isnan(x) or abs(x) > limit_abs


def pretty_percent(x, limit_abs=1e7, limit_text='N/A %', signed=True):
    if too_big(x, limit_abs):
        return limit_text
    return pretty_money(x, postfix=' %', signed=signed)


def round_half_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.floor(n * multiplier + 0.5) / multiplier


def detect_decimal_digits(x):
    x = abs(x)
    if x > 1.0:
        return 0
    return -int(math.floor(math.log10(x)))


def short_money(x, prefix='', postfix='', localization=None, signed=False, integer=False):
    if math.isnan(x):
        return str(x)

    if x == 0:
        zero = '0' if integer else '0.0'
        return f'{prefix}{zero}{postfix}'

    if hasattr(localization, 'SHORT_MONEY_LOC'):
        localization = localization.SHORT_MONEY_LOC
    localization = localization or {}

    if x < 0:
        sign = '-'
        x = -x
    else:
        sign = '+' if signed and x >= 0 else ''

    orig_x = x

    if x < 1_000:
        key = ''
    elif x < 1_000_000:
        x /= 1_000
        key = 'K'
    elif x < 1_000_000_000:
        x /= 1_000_000
        key = 'M'
    elif x < 1_000_000_000_000:
        x /= 1_000_000_000
        key = 'B'
    else:
        x /= 1_000_000_000_000
        key = 'T'

    letter = localization.get(key, key) if localization else key

    if orig_x < 1:
        digits = detect_decimal_digits(orig_x) + 2
        x = f"{x:.{digits}f}".rstrip('0')
    else:
        if integer:
            x = int(x)
        else:
            x = round_half_up(x, 1)

    result = f'{x}{letter}'
    return f'{sign}{prefix}{result}{postfix}'


def short_dollar(x, localization=None, signed=False):
    return short_money(x, prefix='$', localization=localization, signed=signed)


def short_rune(x, localization=None):
    return short_money(x, postfix=RAIDO_GLYPH, localization=localization)


def short_address(address, begin=7, end=4, filler='...'):
    address = str(address)
    if len(address) > begin + end:
        components = []
        if begin:
            components.append(address[:begin])
        if end:
            components.append(address[-end:])
        return filler.join(components)
    else:
        return address


def format_percent(x, total=1.0, signed=False, threshold=0.01):
    if total <= 0:
        s = 0
    else:
        s = x / total * 100.0

    if abs(s) < threshold:  # threshold is %
        return '0 %'

    return pretty_money(s, signed=signed) + " %"


def adaptive_round_to_str(x, force_sign=False, prefix=''):
    ax = abs(x)
    sign = ('+' if force_sign else '') if x > 0 else '-'
    sign = prefix + sign
    if ax < 1.0:
        return f"{sign}{ax:.2f}"
    elif ax < 10.0:
        return f"{sign}{ax:.1f}"
    else:
        return f"{sign}{pretty_money(ax)}"


def calc_percent_change(old_value, new_value):
    return 100.0 * (new_value - old_value) / old_value if old_value and new_value else 0.0


@dataclass
class Asset:
    chain: str = ''
    name: str = ''
    tag: str = ''
    is_synth: bool = False

    @property
    def valid(self):
        return bool(self.chain) and bool(self.name)

    def __post_init__(self):
        if self.chain and not self.name:
            source = self.chain
            a = self.from_string(source)
            self.chain = a.chain
            self.name = a.name
            self.tag = a.tag
            self.is_synth = a.is_synth

    @staticmethod
    def get_name_tag(name_and_tag_str):
        components = name_and_tag_str.split('-', maxsplit=2)
        if len(components) == 2:
            return components
        else:
            return name_and_tag_str, ''

    @classmethod
    def from_string(cls, asset: str):
        try:
            if asset == 'rune':
                return cls('THOR', 'RUNE')
            is_synth = '/' in asset
            chain, name_and_tag = asset.split('/' if is_synth else '.', maxsplit=2)
            name, tag = cls.get_name_tag(name_and_tag)
            return cls(str(chain).upper(), str(name).upper(), str(tag).upper(), is_synth)
        except (IndexError, TypeError, ValueError):
            return cls(name=asset)

    @property
    def short_str(self):
        s = 'Synth:' if self.is_synth else ''
        if self.tag:
            short_tag = self.tag[:6]
            return f'{s}{self.chain}.{self.name}-{short_tag}'
        else:
            return f'{s}{self.chain}.{self.name}'

    @property
    def shortest(self):
        return f'{self.chain}.{self.name}'

    @property
    def full_name(self):
        if self.valid:
            return f'{self.name}-{self.tag}' if self.tag else self.name
        else:
            return self.name

    @property
    def first_filled_component(self):
        return self.chain or self.name or self.tag

    @property
    def native_pool_name(self):
        return f'{self.chain}.{self.full_name}' if self.valid else self.name

    def __str__(self):
        return self.native_pool_name

    @classmethod
    def to_L1_pool_name(cls, asset: str):
        return cls.from_string(asset).native_pool_name

    @property
    def is_gas_asset(self):
        return not self.tag and (
                self.chain == self.name or
                (self.chain == Chains.ATOM and self.name == 'ATOM')
        )


def weighted_mean(values, weights):
    return sum(values[g] * weights[g] for g in range(len(values))) / sum(weights)


def clamp(x, min_x, max_x):
    return min(max(x, min_x), max_x)


POSTFIX_MULTIPLITER = {
    'k': 10 ** 3,
    'm': 10 ** 6,
    'b': 10 ** 9,
    'q': 10 ** 12
}


def parse_short_number(n: str):
    n = str(n).strip().lower()
    if not n:
        return 0.0
    mult = POSTFIX_MULTIPLITER.get(n[-1], 1)
    if mult > 1:
        n = n[:-1]
    return float(n) * mult


class DepthCurve:
    DEPTH = 'depth'
    PERCENT = 'percent'
    SHARE = 'share'

    DEFAULT_TX_VS_DEPTH_CURVE = [
        {DEPTH: 10_000, PERCENT: 12},  # if depth < 10_000 then 0.2
        {DEPTH: 100_000, PERCENT: 8},  # if 10_000 <= depth < 100_000 then 0.2 ... 0.12
        {DEPTH: 1_000_000, PERCENT: 4},  # and so on...
        {DEPTH: 10_000_000, PERCENT: 2},
    ]

    @classmethod
    def default(cls):
        return cls(cls.DEFAULT_TX_VS_DEPTH_CURVE)

    def __init__(self, points: List[dict]):
        self.points = points
        for p in self.points:
            p[self.DEPTH] = parse_short_number(p[self.DEPTH])
            p[self.SHARE] = 0.01 * p[self.PERCENT]

    def evaluate(self, x):
        curve = self.points

        if not curve:
            return 0.0

        lower_bound = 0
        lower_percent = curve[0][self.SHARE]
        for curve_entry in curve:
            upper_bound = curve_entry[self.DEPTH]
            upper_percent = curve_entry[self.SHARE]
            if x < upper_bound:
                return linear_transform(x, lower_bound, upper_bound, lower_percent, upper_percent)
            lower_percent = upper_percent
            lower_bound = upper_bound
        return curve[-1][self.SHARE]
