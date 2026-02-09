import asyncio
import time
from abc import ABCMeta, abstractmethod
from typing import TypeVar, Optional, Generic

from lib.logs import WithLogger

# Define a type variable for the data payload
T = TypeVar("T")


class CachedDataSource(Generic[T], WithLogger, metaclass=ABCMeta):
    def __init__(self, cache_period: float, retry_times: int = 3, retry_delay: float = 1.0,
                 retry_exponential_growth_factor: float = 1.5):
        super().__init__()
        self.cache_period = cache_period
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.retry_exponential_growth_factor = retry_exponential_growth_factor
        self._last_load_time = 0.0
        self._cache: Optional[T] = None
        self._load_lock = asyncio.Lock()

    @abstractmethod
    async def _load(self, *args, **kwargs) -> T:
        ...

    @property
    def is_fresh(self) -> bool:
        """Check if the cached data is still fresh."""
        return self._cache is not None and (time.time() - self._last_load_time) < self.cache_period

    async def get(self, forced=False, *args, **kwargs) -> T:
        now = time.time()

        # If we have cached data, and it's still fresh, return it
        if self.is_fresh and not forced:
            age = now - self._last_load_time
            self.logger.debug(f"Returning cached data (age: {age:.2f}s)")
            return self._cache

        # Ensure only one coroutine refreshes the cache
        async with self._load_lock:
            # Check again in case another task refreshed while waiting
            now = time.time()
            if self.is_fresh and not forced:
                age = now - self._last_load_time
                self.logger.debug(f"Cache refreshed by another task; returning updated data (age: {age:.2f}s)")
                return self._cache

            last_exception = None
            for attempt in range(1, self.retry_times + 1):
                try:
                    if attempt > 1:
                        self.logger.info(f"Loading data (attempt {attempt}/{self.retry_times})...")
                    data = await self._load(*args, **kwargs)

                    # On success, cache it and update timestamp
                    self._cache = data
                    self._last_load_time = time.time()
                    elapsed = self._last_load_time - now
                    self.logger.info(f"Data loaded successfully in {elapsed:.2f}s.")
                    return data

                except Exception as e:
                    last_exception = e
                    self.logger.warning(f"Load attempt {attempt} failed: {e}", exc_info=True)

                    if attempt < self.retry_times:
                        delay = self.retry_delay * (self.retry_exponential_growth_factor ** (attempt - 1))
                        self.logger.debug(f"Sleeping for {delay:.2f}s before retrying...")
                        await asyncio.sleep(delay)

            # All retries failed
            self.logger.error(f"All {self.retry_times} load attempts failed; raising last exception.")
            raise last_exception
