from math import floor, log10

EMOJI_SCALE = [
    # negative
    (-50, '💥'), (-35, '👺'), (-25, '😱'), (-20, '😨'), (-15, '🥵'), (-10, '😰'), (-5, '😢'), (-3, '😥'), (-2, '😔'),
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


def pretty_money(x, prefix='', signed=False):
    if x < 0:
        return f"-{prefix}{pretty_money(-x)}"
    elif x == 0:
        r = "0.0"
    else:
        if x < 100:
            r = str(round_to_dig(x, 3))
        elif x < 1000:
            r = str(round_to_dig(x, 4))
        else:
            r = number_commas(int(round(x)))
    prefix = f'+{prefix}' if signed else prefix
    return prefix + r


def short_money(x, prefix='$'):
    if x < 0:
        return f"-{prefix}{short_money(-x, prefix='')}"
    elif x == 0:
        r = '0.0'
    elif x < 1_000:
        r = f'{x:.1f}'
    elif x < 1_000_000:
        x /= 1_000
        r = f'{x:.1f}K'
    elif x < 1_000_000_000:
        x /= 1_000_000
        r = f'{x:.1f}M'
    else:
        x /= 1_000_000_000
        r = f'{x:.1f}B'
    return prefix + r


def short_address(address, begin=5, end=4, filler='...'):
    address = str(address)
    if len(address) > begin + end:
        return address[:begin] + filler + address[-end:]
    else:
        return address


def format_percent(x, total):
    if total <= 0:
        s = 0
    else:
        s = x / total * 100.0
    if s < 1:
        return f'{s:.3f} %'
    else:
        return f'{s:.1f} %'


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


def short_asset_name(pool: str):
    try:
        cs = pool.split('.')
        return cs[1].split('-')[0]
    except IndexError:
        return pool


def asset_name_cut_chain(asset):
    try:
        cs = asset.split('.')
        return cs[1]
    except IndexError:
        return asset


def weighted_mean(values, weights):
    return sum(values[g] * weights[g] for g in range(len(values))) / sum(weights)
