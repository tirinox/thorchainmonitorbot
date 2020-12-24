import itertools

from services.lib.money import pretty_money


def bold(text):
    return f"<b>{text}</b>"


def link(url, text):
    return f'<a href="{url}">{text}</a>'


def code(text):
    return f"<code>{text}</code>"


def ital(text):
    return f"<i>{text}</i>"


def pre(text):
    return f"<pre>{text}</pre>"


def x_ses(one, two):
    if one == 0 or two == 0:
        return 'N/A'
    else:
        sign = 'x' if two > one else '-x'
        times = two / one if two > one else one / two
        return f'{sign}{pretty_money(times)}'


def progressbar(x, total, symbol_width=10):
    if total <= 0:
        s = 0
    else:
        s = int(round(symbol_width * x / total))
    s = max(0, s)
    s = min(symbol_width, s)
    return '▰' * s + '▱' * (symbol_width - s)


def grouper(n, iterable):
    args = [iter(iterable)] * n
    return ([e for e in t if e is not None] for t in itertools.zip_longest(*args))
