import asyncio
import dataclasses
import datetime
import hashlib
import inspect
import itertools
import json
import logging
import os
import pickle
import random
import re
import string
import time
from bisect import bisect_left
from collections import deque, Counter, defaultdict
from functools import wraps, partial
from io import BytesIO
from itertools import tee
from typing import Iterable, List, Any, Awaitable
from urllib.parse import urlparse, urlunparse

import binascii
from pydantic import BaseModel
from tqdm import tqdm

from lib.date_utils import today_str


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
    if other_str:
        elements.append((other_str, others_sum))
    return elements


def most_common(values: list):
    if not values:
        return
    counter = Counter(values)
    [(v, n)] = counter.most_common(1)
    return v


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
        # noinspection PyTypeChecker
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
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            logging.info(f'Saving pickle to "{path}"...')
            # noinspection PyTypeChecker
            pickle.dump(data, f)
            logging.info(f'Saving pickle to "{path}" done!')


def random_hex(length=12, sharp=False):
    r = binascii.hexlify(os.urandom(length))
    return f'#{r.decode()}' if sharp else r


def generate_random_code(length):
    characters = string.ascii_letters + string.digits
    random_code = ''.join(random.choice(characters) for _ in range(length))
    return random_code


def random_ip_address():
    return ".".join(str(random.randint(0, 255)) for _ in range(4))


def random_chance(percent):
    return random.uniform(0, 100) < percent


def chance_50():
    return random_chance(50)


# noinspection PyTypeChecker
def parse_list_from_string(text: str, upper=False, lower=False, strip=True):
    items = re.split('[;,\n\t]', text)

    if lower:
        items = map(str.lower, items)
    elif upper:
        items = map(str.upper, items)

    if strip:
        items = map(str.strip, items)

    return [x for x in items if x]


def invert_dict_of_iterables(d: dict, factory=set, op=set.add):
    result = defaultdict(factory)
    for k, v in d.items():
        for item in v:
            # noinspection PyArgumentList
            op(result[item], k)
    return dict(result)


def invert_dict(d: dict):
    return dict(zip(d.values(), d.keys()))


def nested_set(dic, keys, value):
    if not keys:
        raise KeyError
    original = dic
    for key in keys[:-1]:
        dic = dic.setdefault(key, {})
    dic[keys[-1]] = value
    return original


def nested_get(dic, keys, default=None):
    if not keys:
        return default
    for key in keys[:-1]:
        dic = dic.get(key, {})
    return dic.get(keys[-1], default)


def tree_factory():
    return defaultdict(tree_factory)


def make_nested_default_dict(d):
    if not isinstance(d, dict):
        return d
    return defaultdict(tree_factory, {k: make_nested_default_dict(v) for k, v in d.items()})


def estimate_max_by_committee(data, minimal_members=3, on_fail_return_max=True):
    c = Counter(data)
    mc = c.most_common()
    mc.sort(reverse=True)  # sort Max value -> Min value
    for value, count in mc:
        if count >= minimal_members:
            return value

    if on_fail_return_max and mc:
        return mc[0][0]


def unique_ident(args, prec='full'):
    items = [today_str(prec), *map(str, args)]
    full_string = ''.join(items)
    return hashlib.md5(full_string.encode()).hexdigest()


def iterable_but_not_str(it):
    return not isinstance(it, (str, bytes)) and isinstance(it, Iterable)


class TooManyTriesException(Exception):
    pass


def retries(times):
    assert times > 0

    def func_wrapper(f):
        async def wrapper(*args, **kwargs):
            outer_exc = None
            for time_no in range(wrapper.times):
                # noinspection PyBroadException
                try:
                    return await f(*args, **kwargs)
                except Exception as exc:
                    outer_exc = exc
                logging.warning(f'Retrying {f} for {time_no + 1} time...')
            raise TooManyTriesException() from outer_exc

        wrapper.times = times
        return wrapper

    return func_wrapper


def copy_photo(p: BytesIO):
    p.seek(0)
    new = BytesIO(p.read())
    new.name = p.name
    return new


def run_once(f):
    """Runs a function (successfully) only once.
    The running can be reset by setting the `has_run` attribute to False
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper._f_res = f(*args, **kwargs)
            wrapper.has_run = True
        return wrapper._f_res

    wrapper.has_run = False
    wrapper._f_res = None
    return wrapper


def run_once_async(f):
    """Runs a function (successfully) only once (async).
    The running can be reset by setting the `has_run` attribute to False
    """

    @wraps(f)
    async def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper._f_res = await f(*args, **kwargs)
            wrapper.has_run = True
            return wrapper._f_res

    wrapper._f_res = None
    wrapper.has_run = False
    return wrapper


nested_dict = lambda: defaultdict(nested_dict)


def safe_get(dct, *keys):
    for key in keys:
        try:
            dct = dct[key]
        except (KeyError, TypeError):
            return None
    return dct


class Buffer:
    def __init__(self, size=10):
        self.buffer = []
        self.size = size

    def add(self, data) -> List[Any]:
        self.buffer.append(data)
        if len(self.buffer) >= self.size:
            contents = self.buffer
            self.buffer = []
            return contents
        else:
            return []


def json_cached_to_file_async(filename):
    def decorator(func):
        @wraps(func)
        async def inner(*args, **kwargs):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except Exception:
                result = await func(*args, **kwargs)
                with open(filename, 'w') as f:
                    # noinspection PyTypeChecker
                    json.dump(result, f)
                return result

        return inner

    return decorator


def load_json(filepath):
    with open(filepath, 'r') as fp:
        return json.load(fp)


def vertical_text(t: str):
    return '\n'.join(t)


def filter_kwargs_according_function_signature(dict_to_filter, thing_with_kwargs, default=None):
    sig = inspect.signature(thing_with_kwargs)
    filter_keys = [param.name for param in sig.parameters.values() if param.kind == param.POSITIONAL_OR_KEYWORD]
    return {filter_key: dict_to_filter.get(filter_key, default) for filter_key in filter_keys}


def take_closest(sorted_list, target, ignore_outliers=False):
    """
    Assumes sorted_list is sorted. Returns closest value to target.

    If two numbers are equally close, return the smallest number.
    """
    if not sorted_list:
        return

    if ignore_outliers:
        if target < sorted_list[0] or target > sorted_list[-1]:
            return

    pos = bisect_left(sorted_list, target)
    if pos == 0:
        return sorted_list[0]
    if pos == len(sorted_list):
        return sorted_list[-1]
    before = sorted_list[pos - 1]
    after = sorted_list[pos]
    return after if after - target < target - before else before


def pluck(list_of_dict, key, default=0.0):
    return [item.get(key, default) for item in list_of_dict]


def pluck_from_series(series, key, default=0.0):
    return [
        (ts, dic.get(key, default) if dic else default) for ts, dic in series
    ]


def paste_at_beginning_of_dict(d: dict, k, v):
    if k in d:
        del d[k]
    return {
        **{k: v},
        **d
    }


def str_to_bytes(s: str):
    if s.startswith('0x') or s.startswith('0X'):
        s = s[2:]
    return bytes.fromhex(s)


async def parallel_run_in_groups(
        tasks: List[Awaitable[Any]],
        group_size: int = 10,
        delay: float = 0.0,
        use_tqdm: bool = False
) -> List[Any]:
    if not tasks:
        return []

    groups = list(grouper(group_size, tasks))
    results = []

    pbar = tqdm(total=len(tasks), desc="Processing tasks") if use_tqdm and tqdm else None

    for group in groups:
        group_results = await asyncio.gather(*group)
        results.extend(group_results)
        if pbar:
            pbar.update(len(group))
        if delay > 0:
            await asyncio.sleep(delay)

    if pbar:
        pbar.close()

    return results


def grouper(n, iterable):
    args = [iter(iterable)] * n
    # noinspection PyArgumentList
    return ([e for e in t if e is not None] for t in itertools.zip_longest(*args))


def is_list_of_type(lst, type_):
    try:
        return lst and all(isinstance(item, type_) for item in lst)
    except TypeError:
        return False


def is_named_tuple_instance(x):
    t = type(x)
    b = t.__bases__
    if len(b) != 1 or b[0] != tuple:
        return False
    f = getattr(t, '_fields', None)
    if not isinstance(f, tuple):
        return False
    return all(type(n) == str for n in f)


def add_properties_to_representation(repr, obj):
    # Add properties dynamically
    for attr in dir(obj):
        # Check if it's a property and not private or already in the result
        if (
                not attr.startswith("_") and
                not attr in repr and
                isinstance(getattr(type(obj), attr, None), property)
        ):
            repr[attr] = getattr(obj, attr)
    return repr


def _to_plain(obj: Any, add_properties: bool):
    """Phase 1: turn dataclasses/namedtuples into dicts/lists/primitives, recursively."""
    if is_named_tuple_instance(obj):
        fields = {k: _to_plain(v, add_properties) for k, v in obj._asdict().items()}
        return add_properties_to_representation(fields, obj) if add_properties else fields

    if dataclasses.is_dataclass(obj):
        fields = {k: _to_plain(v, add_properties) for k, v in dataclasses.asdict(obj).items()}
        return add_properties_to_representation(fields, obj) if add_properties else fields

    if isinstance(obj, (list, tuple, set)):
        return [_to_plain(v, add_properties) for v in obj]

    if isinstance(obj, dict):
        return {k: _to_plain(v, add_properties) for k, v in obj.items()}

    if isinstance(obj, BaseModel):
        # Pydantic v2 support
        dump = obj.model_dump()
        return {k: _to_plain(v, add_properties) for k, v in dump.items()}

    # primitives (int/str/float/bool/None/datetime/etc.) pass through for phase 2
    return obj


def _ensure_ts(dt: datetime.datetime) -> int:
    """Robust UNIX timestamp; treat naive datetimes as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp())


def _inject_datetime_ts(obj: Any):
    """
    Phase 2: recursively convert datetimes to ISO strings everywhere.
    Additionally, when a datetime appears as a dict value, inject <key>_ts with UNIX timestamp.
    """
    # datetime directly
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()

    # list-like
    if isinstance(obj, list):
        return [_inject_datetime_ts(v) for v in obj]

    # dict-like: handle values and add *_ts alongside datetime values
    if isinstance(obj, dict):
        out = {}
        # stage 1: transform values
        for k, v in obj.items():
            if isinstance(v, datetime.datetime):
                out[k] = v.isoformat()
                out[f"{k}_ts"] = _ensure_ts(v)
            else:
                out[k] = _inject_datetime_ts(v)
        return out

    # everything else unchanged
    return obj


def recursive_asdict(j, add_properties=False, handle_datetime=False):
    """
        Convert complex objects to plain structures.
        If handle_datetime=True:
          - Every datetime becomes ISO string everywhere
          - When a datetime is a dict value, also add <key>_ts with UNIX timestamp
        """
    try:
        plain = _to_plain(j, add_properties)
        return _inject_datetime_ts(plain) if handle_datetime else plain
    except TypeError:
        logging.error(f'Failed to convert {j!r} to plain dict/list/primitives!')
        logging.error(f'HEX: {obj_to_hex(j)}')
        raise


def strip_trailing_slash(s: str):
    return s.rstrip('/')


async def say(msg: str):
    if msg:
        msg = msg.replace('"', '').replace('\\b', '')

        def worker():
            os.system('afplay /System/Library/Sounds/Sosumi.aiff')
            os.system(f'say "{msg}"')

        async def a_worker():
            # noinspection PyTypeChecker
            await asyncio.get_event_loop().run_in_executor(None, worker)

        # noinspection PyAsyncCall
        asyncio.create_task(a_worker())


def hash_of_string_repr(*obj):
    dump = ''.join(str(o) for o in obj)
    return hashlib.sha256(dump.encode()).hexdigest().upper()


def expect_bytes(o):
    return o if isinstance(o, bytes) else str(o).encode('utf-8')


def expect_string(o):
    return o if isinstance(o, str) else o.decode('utf-8')


def translate(s: str, d: dict):
    for k, v in d.items():
        s = s.replace(k, v)
    return s


def get_ttl_hash(seconds=3600):
    """Return the same value withing `seconds` time period"""
    return round(time.time() / seconds)


def filter_none_values(d: dict):
    return {k: v for k, v in d.items() if v is not None}


def identity(x):
    return x


def remove_path_and_query(url):
    parsed_url = urlparse(url)
    clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, '', '', '', ''))
    return clean_url


async def gather_in_batches(tasks: List[Awaitable[Any]], batch_size: int) -> List[Any]:
    """
    Gather asyncio tasks in batches to avoid overwhelming the system.

    Args:
        tasks (List[Awaitable[Any]]): A list of awaitable objects or coroutines.
        batch_size (int): The number of tasks to process concurrently in each batch.

    Returns:
        List[Any]: A list of results from the tasks.
    """
    results = []
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        batch_results = await asyncio.gather(*batch)
        results.extend(batch_results)
    return results


def namedtuple_to_dict(obj) -> dict:
    """
    Converts a NamedTuple instance to a dictionary including its fields and properties.
    For each field or property, if the value is not JSON serializable,
    it is replaced with a string like "<TypeName> not JSON-serializable".

    Args:
        obj (NamedTuple): The NamedTuple instance to convert.

    Returns:
        dict: A dictionary representation of the NamedTuple, with non-serializable
              objects replaced by a descriptive string.
    """

    # Check that the object is a NamedTuple instance.
    if not is_named_tuple_instance(obj):
        raise TypeError("Input must be an instance of NamedTuple.")

    # Helper to check JSON serialization ability
    def is_json_serializable(value):
        try:
            json.dumps(value)
            return True
        except (TypeError, OverflowError):
            return False

    # Helper to recursively convert values
    def convert_value(value):
        if is_named_tuple_instance(value):
            return namedtuple_to_dict(value)
        elif isinstance(value, dict):
            # Recursively process each key/value in the dictionary.
            return {key: convert_value(val) for key, val in value.items()}
        elif isinstance(value, (list, tuple)):
            # Process items in lists/tuples.
            return [convert_value(item) for item in value]
        else:
            # For non-iterable values, check if they are JSON serializable.
            if is_json_serializable(value):
                return value
            elif hasattr(value, 'to_dict'):
                # If the object has a to_dict method, call it.
                return convert_value(value.to_dict())
            else:
                # Replace non-serializable object with a descriptive string.
                return f"{type(value).__name__} not JSON-serializable"

    # Convert the NamedTuple to a dictionary using _asdict()
    result = obj._asdict()

    # Add any properties that are not already in the result.
    for attr in dir(obj):
        if (
                not attr.startswith("_") and
                attr not in result and
                isinstance(getattr(type(obj), attr, None), property)
        ):
            result[attr] = getattr(obj, attr)

    # Recursively check every value in the dictionary for JSON serializability.
    result = {key: convert_value(value) for key, value in result.items()}

    return result


_GLB_HIT_COUNTER = {}


def hit_every(key: str, n: int) -> bool:
    g = _GLB_HIT_COUNTER
    if key not in g:
        g[key] = 0
    g[key] += 1
    if g[key] >= n:
        g[key] = 0
        return True
    return False


def shorten_json(data):
    if isinstance(data, list):
        if len(data) > 4:
            return [
                shorten_json(data[0]),
                shorten_json(data[1]),
                [f"{len(data) - 3} items more..."],
                shorten_json(data[-1]),
            ]
        else:
            return [shorten_json(item) for item in data]
    elif isinstance(data, dict):
        if all(isinstance(v, dict) for v in data.values()) and len(data) > 4:
            keys = list(data.keys())
            shortened_dict = {k: shorten_json(data[k]) for k in (keys[:2] + [keys[-1]])}
            shortened_dict[""] = f"{len(data) - 3} keys more..."
            return shortened_dict
        else:
            return {k: shorten_json(v) for k, v in data.items()}
    else:
        return data


def sizeof_fmt(num: int, suffix="B") -> str:
    """Convert bytes to human-readable format (KB, MB, GB, etc.)."""
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Y{suffix}"


def obj_to_hex(obj: Any, *, protocol: int = pickle.HIGHEST_PROTOCOL) -> str:
    """
    Pickle a Python object and return a hex-encoded string.

    :param obj: Any picklable Python object.
    :param protocol: Pickle protocol to use (default: highest available).
    :return: Hex string (lowercase) representing the pickled bytes.
    """
    data = pickle.dumps(obj, protocol=protocol)
    return data.hex()


def hex_to_obj(hex_str: str) -> Any:
    """
    Decode a hex string produced by `obj_to_hex` and unpickle the object.

    :param hex_str: Hex string of pickled data.
    :return: The original Python object.
    :raises ValueError: If the hex string is invalid.
    :raises pickle.UnpicklingError: If unpickling fails.
    """
    try:
        data = bytes.fromhex(hex_str.strip())
    except ValueError as e:
        raise ValueError("Invalid hex string: not valid hexadecimal.") from e

    return pickle.loads(data)
