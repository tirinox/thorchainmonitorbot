import time
from datetime import datetime
from functools import wraps
from math import floor, log10

MINUTE = 60
HOUR = 60 * 60
DAY = 24 * 60 * 60
MONTH = 30 * 24 * 60 * 60


def now_ts() -> float:
    return datetime.now().timestamp()  # don't use utcnow() since timestamp() does this conversion


def seconds_diff(t1: datetime, t2: datetime) -> float:
    return (t1 - t2).total_seconds()


def seconds_human(seconds, equal_str='same time') -> str:
    seconds = int(seconds)

    def append_if_not_zero(acc, val, time_type):
        return acc if val == 0 else "{} {} {}".format(acc, val, time_type)

    if seconds == 0:
        return equal_str
    else:
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24

        s = ''
        s = append_if_not_zero(s, days, 'd')
        if days <= 31:
            s = append_if_not_zero(s, hours % 24, 'h')
        if not days:
            s = append_if_not_zero(s, minutes % 60, 'min')
        if not hours:
            s = append_if_not_zero(s, seconds % 60, 'sec')
        return s.strip()


LONG_AGO = datetime(1980, 1, 1)


def parse_timespan_to_seconds(span: str):
    try:
        return int(span)
    except ValueError:
        result = 0
        str_for_number = ''
        for symbol in span:
            symbol = symbol.lower()
            if symbol in ['d', 'h', 'm', 's']:
                if str_for_number:
                    try:
                        number = int(str_for_number)
                    except ValueError:
                        return 'Error! Invalid number: {}'.format(str_for_number)
                    else:
                        multipliers = {
                            's': 1,
                            'm': 60,
                            'h': 3600,
                            'd': 3600 * 24
                        }
                        result += multipliers[symbol] * number
                    finally:
                        str_for_number = ''
                else:
                    return 'Error! Must be some digits before!'
            elif symbol in [chr(i + ord('0')) for i in range(10)]:
                str_for_number += symbol
            elif symbol in [' ', ',', ';', ':', '\t', '/', '.']:
                pass
            else:
                return 'Error! Unexpected symbol: {}'.format(symbol)

        if str_for_number:
            return 'Error! Unfinished component in the end: {}'.format(str_for_number)

        return result


def format_time_ago(d):
    if d is None or d == 0:
        return 'never'
    else:
        return f'{seconds_human(now_ts() - d)} ago'


def a_result_cached(ttl=60):
    def decorator(func):
        last_update_ts = -1.0
        last_result = None

        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal last_result, last_update_ts
            if last_update_ts < 0 or time.monotonic() - ttl > last_update_ts:
                last_result = await func(*args, **kwargs)
                last_update_ts = time.monotonic()
            return last_result

        return wrapper

    return decorator


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


def pretty_money(x):
    if x < 0:
        return "-" + pretty_money(-x)
    elif x == 0:
        return "0.0"
    else:
        if x < 100:
            return str(round_to_dig(x, 2))
        else:
            return number_commas(int(round(x)))


def bold(text):
    return f"<b>{text}</b>"


def link(url, text):
    return f'<a href="{url}">{text}</a>'


def code(text):
    return f"<code>{text}</code>"


def pre(text):
    return f"<pre>{text}</pre>"


def x_ses(one, two):
    if one == 0 or two == 0:
        return 'N/A'
    else:
        sign = 'x' if two > one else '-x'
        times = two / one if two > one else one / two
        return f'{sign}{pretty_money(times)}'


def short_address(address, begin=5, end=4, filler='...'):
    address = str(address)
    if len(address) > begin + end:
        return address[:begin] + filler + address[-end:]
    else:
        return address


def progressbar(x, total, symbol_width=10):
    if total <= 0:
        s = 0
    else:
        s = int(round(symbol_width * x / total))
    s = max(0, s)
    s = min(symbol_width, s)
    return '▰' * s + '▱' * (symbol_width - s)


def format_percent(x, total):
    if total <= 0:
        s = 0
    else:
        s = x / total * 100.0
    if s < 1:
        return f'{s:.3f} %'
    else:
        return f'{s:.1f} %'


def adaptive_round_to_str(x, force_sign=False):
    ax = abs(x)
    sign = ('+' if force_sign else '') if x > 0 else '-'
    if ax < 1.0:
        return f"{sign}{ax:.2f}"
    elif ax < 10.0:
        return f"{sign}{ax:.1f}"
    else:
        return f"{sign}{pretty_money(ax)}"


EMOJI_SCALE = [
    # negative
    (-50, '💥'), (-35, '👺'), (-25, '😱'), (-20, '😨'), (-15, '🥵'), (-10, '😰'), (-5, '😢'), (-3, '😥'), (-2, '😔'),
    (-1, '😑'), (0, '😕'),
    # positive
    (1, '😏'), (2, '😄'), (3, '😀'), (5, '🤗'), (10, '🍻'), (15, '🎉'), (20, '💸'), (25, '🔥'), (35, '🌙'), (50, '🌗'),
    (65, '🌕'), (80, '⭐'), (100, '✨'), (10000000, '🚀⚡')
]


def calc_percent_change(old_value, new_value):
    return 100.0 * (new_value - old_value) / old_value if old_value and new_value else 0.0


def emoji_for_percent_change(pc):
    for threshold, emoji in EMOJI_SCALE:
        if pc <= threshold:
            return emoji
    return EMOJI_SCALE[-1]  # last one
