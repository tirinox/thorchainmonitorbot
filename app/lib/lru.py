from collections import deque
from statistics import median

from lib.date_utils import now_ts


class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache = {}
        self._deque = deque()

    def get(self, key):
        if key in self._cache:
            self._deque.remove(key)
            self._deque.append(key)
            return self._cache[key]

    def set(self, key, value):
        if self.get(key):
            self._cache[key] = value
        else:
            if len(self._deque) >= self.capacity:
                oldest = self._deque.popleft()
                del self._cache[oldest]
            self._deque.append(key)
            self._cache[key] = value

    def __repr__(self):
        return f'LRUCache({self.capacity}, size={len(self._cache)})'

    def __setitem__(self, key, value):
        return self.set(key, value)

    def __getitem__(self, key):
        return self.get(key)

    def __contains__(self, item):
        return item in self._cache

    def values(self):
        return self._cache.values()


class WindowAverage:
    def __init__(self, window_size: int):
        self._values = deque(maxlen=window_size)

    @property
    def __len__(self):
        return len(self._values)

    def append(self, value):
        self._values.append(value)

    @property
    def average(self):
        return sum(self._values) / len(self._values) if self._values else None

    @property
    def min(self):
        return min(self._values) if self._values else None

    @property
    def max(self):
        return max(self._values) if self._values else None

    @property
    def median(self):
        return median(self._values) if self._values else None


class RPSCounter:
    def __init__(self, window_size=60, max_requests=10_000):
        self.requests = deque()  # Use a deque to store request timestamps
        self.window_size = window_size  # N minutes converted to seconds
        self.max_requests = max_requests  # Adjust as needed

    def add_request(self):
        current_time = now_ts()
        self.requests.append(current_time)

        # Remove requests that are outside the window
        while self.requests and current_time - self.requests[0] > self.window_size:
            self.requests.popleft()

    def get_rps(self):
        # Calculate RPS by dividing the number of requests in the window by the window size
        return len(self.requests) / self.window_size
