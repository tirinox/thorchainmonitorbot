import asyncio
import binascii
import logging
import operator
import os
import pickle
import random
import re
import time
from collections import deque, Counter, defaultdict
from functools import wraps, partial
from itertools import tee
from typing import List


def most_common_and_other(values: list, max_categories, other_str='Others'):
    """
    Count categories in the values, if there are more than max_categories, sum up all others to other_str field
    Returns: List of most common elements ( [name, count_of_occur], [name_2, count_2], ..., ["Others", count_of_others])
    """
    provider_counter = Counter(values)
    total = sum(provider_counter.values())
    elements = provider_counter.most_common(max_categories)
    total_most_common = sum(item[1] for item in elements)
    others_sum = total - total_most_common
    elements.append((other_str, others_sum))
    return elements


def most_common(values: list):
    if not values:
        return
    counter = Counter(values)
    [(v, n)] = counter.most_common(1)
    return v


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
    """
    Shuffle list, go round it, shuffle again.
    Infinite iterator.
    Guaranteed no duplicates (except of border cases sometimes)
    """
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


def make_stickers_iterator(name_list):
    no_dup_list = list(set(name_list))  # remove duplicates
    return circular_shuffled_iterator(no_dup_list)


def setup_logs(log_level):
    logging.basicConfig(
        level=logging.getLevelName(log_level),
        format='%(asctime)s %(levelname)s:%(name)s:%(funcName)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    logging.info('-' * 100)
    logging.info(f"Log level: {log_level}")


def pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ..."""
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def load_pickle(path):
    try:
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                logging.info(f'Loaded pickled data of type {type(data)} from "{path}"')
                return data
    except Exception as e:
        logging.error(f'Failed to load pickled data "{path}"! Error is "{e!r}".')
        return None


def save_pickle(path, data):
    if path:
        with open(path, 'wb') as f:
            logging.info(f'Saving pickle to "{path}"...')
            pickle.dump(data, f)
            logging.info(f'Saving pickle to "{path}" done!')


def random_hex(length=12):
    return binascii.b2a_hex(os.urandom(length))


def random_ip_address():
    return ".".join(str(random.randint(0, 255)) for _ in range(4))


def sep(space=False):
    if space:
        print()
    print('-' * 100)
    if space:
        print()


def class_logger(self):
    return logging.getLogger(self.__class__.__name__)


def parse_list_from_string(text: str, upper=False, lower=False, strip=True):
    items = re.split('[;,\n\t]', text)

    if lower:
        items = map(str.lower, items)
    elif upper:
        items = map(str.upper, items)

    if strip:
        items = map(str.strip, items)

    return [x for x in items if x]


def fuzzy_search(query: str, realm) -> List[str]:
    if not query:
        return []

    query = query.upper()
    if query in realm:  # perfect match
        return [query]

    variants = []
    for name in realm:
        if query in name:
            variants.append(name)
    return variants


def turn_dic_inside_out(d: dict, factory=set, op=set.add):
    result = defaultdict(factory)
    for k, v in d.items():
        for item in v:
            # noinspection PyArgumentList
            op(result[item], k)
    return dict(result)
