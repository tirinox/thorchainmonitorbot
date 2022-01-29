import math
from dataclasses import dataclass
from math import floor, log10

EMOJI_SCALE = [
    # negative
    (-50, '💥'), (-35, '👺'), (-25, '🥵'), (-20, '😱'), (-15, '😨'), (-10, '😰'), (-5, '😢'), (-3, '😥'), (-2, '😔'),
    (-1, '😑'), (0, '😕'),
    # positive
    (1, '😏'), (2, '😄'), (3, '😀'), (5, '🤗'), (10, '🍻'), (15, '🎉'), (20, '💸'), (25, '🔥'), (35, '🌙'), (50, '🌗'),
    (65, '🌕'), (80, '⭐'), (100, '✨'), (10000000, '🚀')
]


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


def pretty_dollar(x):
    return pretty_money(x, '$')


def _number_short_with_postfix_step(x, up, pf, pf_next, precision):
    prec_const = 10 ** precision
    up_exp = 10 ** up
    y = round(x / up_exp * prec_const) / prec_const
    if y == 1000.0:
        return 1.0, pf_next
    else:
        return y, pf


def number_short_with_postfix(x: float, precision=1):
    x = float(x)
    if x < 0:
        return f'-{number_short_with_postfix(-x)}'

    if x < 1e3:
        return f'{x}'
    elif x < 1e6:
        x, postfix = _number_short_with_postfix_step(x, 3, 'K', 'M', precision)
    elif x < 1e9:
        x, postfix = _number_short_with_postfix_step(x, 6, 'M', 'B', precision)
    elif x < 1e12:
        x, postfix = _number_short_with_postfix_step(x, 9, 'B', 'T', precision)
    elif x < 1e15:
        x, postfix = _number_short_with_postfix_step(x, 12, 'T', 'Q', precision)
    else:
        return f'{x:.2E}'

    return f'{x}{postfix}'


def pretty_money(x, prefix='', signed=False, postfix='', short_form=False):
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
            if short_form:
                r = number_short_with_postfix(x)
            else:
                r = number_commas(x)
    prefix = f'+{prefix}' if signed else prefix
    return f'{prefix}{r}{postfix}'


def too_big(x, limit_abs=1e7):
    return math.isinf(x) or math.isnan(x) or abs(x) > limit_abs


def pretty_percent(x, limit_abs=1e7, limit_text='N/A %', signed=True):
    if too_big(x, limit_abs):
        return limit_text
    return pretty_money(x, postfix=' %', signed=signed)


def short_money(x, prefix='', postfix='', localization=None, signed=False):
    if x == 0:
        return f'{prefix}0.0{postfix}'

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
    if orig_x < 10:
        result = f'{x:.2f}{letter}'
    else:
        result = f'{x:.1f}{letter}'
    return f'{sign}{prefix}{result}{postfix}'


def short_dollar(x, localization=None):
    return short_money(x, prefix='$', localization=localization)


def short_address(address, begin=5, end=4, filler='...'):
    address = str(address)
    if len(address) > begin + end:
        return address[:begin] + filler + (address[-end:] if end else '')
    else:
        return address


def format_percent(x, total=1.0, signed=False):
    if total <= 0:
        s = 0
    else:
        s = x / total * 100.0

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

    @property
    def valid(self):
        return bool(self.chain) and bool(self.name)

    def __post_init__(self):
        if self.chain and not self.name:
            a = self.from_string(self.chain)
            self.chain = a.chain
            self.name = a.name
            self.tag = a.tag

    @classmethod
    def from_string(cls, asset: str):
        try:
            chain, name_and_tag = asset.split('.', maxsplit=2)
            components = name_and_tag.split('-', maxsplit=2)
            if len(components) == 2:
                name, tag = components
            else:
                name, tag = name_and_tag, ''
            return cls(str(chain).upper(), str(name).upper(), str(tag).upper())
        except (IndexError, TypeError, ValueError):
            return cls('', asset, '')

    @property
    def short_str(self):
        if self.tag:
            short_tag = self.tag[:6]
            return f'{self.chain}.{self.name}-{short_tag}'
        else:
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

    def __str__(self):
        return f'{self.chain}.{self.full_name}' if self.valid else self.name


def weighted_mean(values, weights):
    return sum(values[g] * weights[g] for g in range(len(values))) / sum(weights)
