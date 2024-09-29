# Copy of https://github.com/iamsinghrajat/async-cache


from collections import OrderedDict
import datetime
from typing import Any


class KEY:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        kwargs.pop("use_cache", None)

    def __eq__(self, obj):
        return hash(self) == hash(obj)

    def __hash__(self):
        def _hash(param: Any):
            if isinstance(param, tuple):
                return tuple(map(_hash, param))
            if isinstance(param, dict):
                return tuple(map(_hash, param.items()))
            elif hasattr(param, "__dict__"):
                return str(vars(param))
            else:
                return str(param)

        return hash(_hash(self.args) + _hash(self.kwargs))


class LRU(OrderedDict):
    def __init__(self, maxsize, *args, **kwargs):
        self.maxsize = maxsize
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self.maxsize and len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]


class AsyncTTL:
    class _TTL(LRU):
        def __init__(self, time_to_live, maxsize):
            super().__init__(maxsize=maxsize)

            self.time_to_live = (
                datetime.timedelta(seconds=time_to_live) if time_to_live else None
            )

            self.maxsize = maxsize

        def __contains__(self, key):
            if key not in self.keys():
                return False
            else:
                key_expiration = super().__getitem__(key)[1]
                if key_expiration and key_expiration < datetime.datetime.now():
                    del self[key]
                    return False
                else:
                    return True

        def __getitem__(self, key):
            value = super().__getitem__(key)[0]
            return value

        def __setitem__(self, key, value):
            ttl_value = (
                (datetime.datetime.now() + self.time_to_live)
                if self.time_to_live
                else None
            )
            super().__setitem__(key, (value, ttl_value))

    def __init__(self, time_to_live=60, maxsize=1024, skip_args: int = 0):
        """
        :param time_to_live: Use time_to_live as None for non expiring cache
        :param maxsize: Use maxsize as None for unlimited size cache
        :param skip_args: Use `1` to skip first arg of func in determining cache key
        """
        self.ttl = self._TTL(time_to_live=time_to_live, maxsize=maxsize)
        self.skip_args = skip_args

    def __call__(self, func):
        async def wrapper(*args, use_cache=True, **kwargs):
            key = KEY(args[self.skip_args:], kwargs)
            if key in self.ttl and use_cache:
                val = self.ttl[key]
            else:
                self.ttl[key] = await func(*args, **kwargs)
                val = self.ttl[key]

            return val

        wrapper.__name__ += func.__name__

        return wrapper
