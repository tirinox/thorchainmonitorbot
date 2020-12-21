import itertools
import time
from functools import wraps
import pandas as pd

from services.lib.money import pretty_money


def series_to_pandas(ts_result, shift_time=True):
    normal_data = []
    zero_t = None
    for key, value_d in ts_result:
        key = key.decode('ascii').split('-')
        event_id = int(key[1])
        if event_id > 99:
            continue

        # ms -> sec; + up to 100 events 0.01 sec each
        time_point = float(key[0]) / 1000.0 + 0.01 * event_id
        if zero_t is None:
            zero_t = time_point

        values = {
            k.decode('ascii'): float(v) for k, v in value_d.items()
        }

        normal_data.append({
            "t": (time_point - zero_t) if shift_time else time_point,
            **values
        })
    return pd.DataFrame(normal_data)


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


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def grouper(n, iterable):
    args = [iter(iterable)] * n
    return ([e for e in t if e is not None] for t in itertools.zip_longest(*args))


def linear_transform(x, low_x, hi_x, low_y, hi_y):
    x_norm = (x - low_x) / (hi_x - low_x)
    return x_norm * (hi_y - low_y) + low_y
