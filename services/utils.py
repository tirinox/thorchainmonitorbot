import asyncio
from functools import wraps
import time
from math import floor, log10


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
    return f"<b>{text}</b"


def link(url, text):
    return f'<a href="{url}">{text}</a>'


def code(text):
    return f"<code>{text}</code>"


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
