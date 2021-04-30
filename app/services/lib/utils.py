import asyncio
import logging
import os
import pickle
import time
from collections import deque
from functools import wraps, partial
import random
from itertools import tee


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


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def linear_transform(x, low_x, hi_x, low_y, hi_y):
    x_norm = (x - low_x) / (hi_x - low_x)
    return x_norm * (hi_y - low_y) + low_y


def async_wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)

    return run


def circular_shuffled_iterator(lst):
    if not lst:
        return None

    lst = list(lst)
    random.shuffle(lst)
    d = deque(lst)
    shifts = 0
    while True:
        yield d[0]
        d.rotate(1)
        shifts += 1
        if shifts >= len(d):
            random.shuffle(d)
            shifts = 0


def setup_logs(log_level):
    logging.basicConfig(
        level=logging.getLevelName(log_level),
        format='%(asctime)s %(levelname)s:%(module)s:%(funcName)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    logging.info('-' * 100)
    logging.info(f"Log level: {log_level}")


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def load_pickle(path):
    try:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                logging.info(f'Loaded pickled data of type {type(data)} from "{path}"')
                return data
    except Exception as e:
        logging.error(f'Failed to load pickled data "{path}"! Error is "{e!r}".')
        return None


def save_pickle(path, data):
    with open(path, 'wb') as f:
        pickle.dump(data, f)
