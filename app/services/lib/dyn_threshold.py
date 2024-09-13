from abc import ABCMeta, abstractmethod
from contextlib import suppress

from services.lib.accumulator import Accumulator
from services.lib.date_utils import HOUR, now_ts
from services.lib.db import DB
from services.lib.logs import WithLogger
from services.lib.money import clamp, sigmoid
from services.models.time_series import TimeSeries


class IDynamicThreshold(WithLogger, metaclass=ABCMeta):
    @abstractmethod
    async def hit(self, value: float):
        pass

    @abstractmethod
    async def clear(self):
        with suppress(Exception):
            r = await self.db.get_redis()
            await r.delete(self.db_key)
            await r.delete(self.db_key_last_adjusted_ts)

    @property
    def db_key(self):
        return f'{self._key}:[dyn_threshold]'

    @property
    def db_key_threshold(self):
        return f'{self.db_key}:threshold'

    @property
    def db_key_last_adjusted_ts(self):
        return f'{self.db_key}:last_adj_ts'

    async def get_last_adjusted_ts(self):
        r = await self.db.get_redis()
        ts = await r.get(self.db_key_last_adjusted_ts)
        return float(ts) if ts is not None else 0.0

    async def get_current_threshold(self) -> float:
        r = await self.db.get_redis()
        threshold = await r.get(self.db_key_threshold)
        return float(threshold) if threshold is not None else self.initial_threshold

    async def set_current_threshold(self, threshold):
        r = await self.db.get_redis()
        await r.set(self.db_key_threshold, threshold)
        await r.set(self.db_key_last_adjusted_ts, now_ts())

    def __init__(self, db: DB, key: str, target_event_number: int,
                 duration_sec: float,
                 initial_threshold: float, min_threshold=0.0, max_threshold=1.0e9):
        super().__init__()
        self._key = key
        self.db = db
        self.target_event_number = target_event_number
        self.estimation_interval_sec = duration_sec
        self.initial_threshold = initial_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        assert self.target_event_number >= 0
        assert self.estimation_interval_sec > 0
        assert self.min_threshold < self.max_threshold


class DynamicThresholdSigmoid(IDynamicThreshold):
    def __init__(self, key, db: DB,
                 target_event_number: int,
                 estimation_interval_sec: float,
                 initial_threshold: float, min_threshold=0.0, max_threshold=1.0e9,
                 adjustment_factor=0.1,
                 adjustment_period=30,
                 acc_tol=HOUR):
        """
        :param key: DB key to distinguish different thresholds
        :param db: DB
        :param target_event_number: Target number of events per TTL
        :param estimation_interval_sec: Time interval to count the events
        :param initial_threshold: Initial threshold value
        :param min_threshold: Minimum threshold value
        :param max_threshold: Maximum threshold value
        :param adjustment_factor: Adjustment factor for the threshold
        :param acc_tol: Accumulator tolerance (default is 1 Hour)
        """
        super().__init__(db, key, target_event_number, estimation_interval_sec, initial_threshold, min_threshold, max_threshold)

        self.adjustment_factor = adjustment_factor
        assert 0.0 < adjustment_factor < 10.0
        self.adjustment_period = adjustment_period
        assert adjustment_period > 0
        self.target_event_number = target_event_number

        assert acc_tol >= 1
        self.accum = Accumulator(self.db_key, db, acc_tol)

    async def get_passed_events(self):
        now = now_ts()
        s = await self.accum.sum(start_ts=now - self.estimation_interval_sec, end_ts=now, key='passed_events')
        return int(s)

    @property
    def oldest_possible_event_ts(self):
        return now_ts() - self.estimation_interval_sec

    def adjust_threshold_fn(self, passed_events, threshold):
        old = threshold

        delta = passed_events - self.target_event_number

        s = (sigmoid(self.adjustment_factor * delta) - 0.5) * 2
        threshold = threshold * (1 + s)

        threshold = clamp(threshold, self.min_threshold, self.max_threshold)
        self.logger.debug(
            f"Threshold: {old} -> {threshold}; Passed events: {passed_events}; Target: {self.target_event_number}"
            f"; Delta: {delta}; Adjustment: {s}")

        return threshold

    async def adjust_threshold(self, threshold):
        passed_events = await self.get_passed_events()
        new_threshold = self.adjust_threshold_fn(passed_events, threshold)
        await self.set_current_threshold(new_threshold)

    async def _increase_and_store(self):
        await self.accum.add_now(passed_events=1)
        await self.accum.clear(self.oldest_possible_event_ts)

    async def hit(self, value: float):
        threshold = await self.get_current_threshold()

        if value >= threshold:
            await self._increase_and_store()

            # if the event passed the threshold, adjust the threshold immediately
            await self.adjust_threshold(threshold)
            return True
        else:
            # if the threshold was not passed, check if it's time to adjust the threshold
            last_adjusted_ts = await self.get_last_adjusted_ts()
            if now_ts() - last_adjusted_ts > self.adjustment_period:
                await self.adjust_threshold(threshold)

            return False

    async def clear(self):
        await super().clear()
        with suppress(Exception):
            await self.accum.clear()


class DynamicThresholdHistory(IDynamicThreshold):
    async def hit(self, value: float) -> bool:
        old_threshold = await self.get_current_threshold()

        await self._series.add(value=value)

        # 1. Compute the threshold from the history
        all_values = await self._series.get_last_values(self.estimation_interval_sec, 'value')
        threshold = self.find_threshold(all_values, self.target_event_number)

        # 2. Amplify the threshold if the number of passed events differs from the target
        n_really_passed = await self.get_passed_events()
        delta = n_really_passed - self.target_event_number
        threshold *= 1 + delta / self.target_event_number * self.delta_amplification

        # 3. Clamp the threshold to the allowed range
        threshold = clamp(threshold, self.min_threshold, self.max_threshold)

        # self.validate_threshold(all_values, threshold)
        self.logger.debug(
            f'Old threshold: {old_threshold}, new threshold: {threshold}, total values: {len(all_values)}')

        await self.set_current_threshold(threshold)

        passed = value >= threshold

        if passed:
            await self._accum.add_now(n=1)

        return passed

    async def clear(self):
        await super().clear()
        with suppress(Exception):
            await self._series.clear()

    def __init__(self, key, db: DB,
                 target_event_number: int,
                 estimation_interval_sec: float,
                 initial_threshold: float, min_threshold=0.0, max_threshold=1.0e9,
                 max_len=100000,
                 delta_amplification=1.0):
        super().__init__(db, key, target_event_number, estimation_interval_sec, initial_threshold, min_threshold,
                         max_threshold)
        self.delta_amplification = delta_amplification
        self._series = TimeSeries(f'{self._key}:[history]', db, max_len=max_len)
        acc_tol = round(estimation_interval_sec / 20)  # 5 %
        self._accum = Accumulator(f'{self._key}:passed', db, acc_tol)

    async def get_passed_events(self):
        now = now_ts()
        s = await self._accum.sum(start_ts=now - self.estimation_interval_sec, end_ts=now, key='n')
        return int(s)

    @staticmethod
    def find_threshold(arr, pass_count):
        # Sort the array in descending order
        sorted_arr = sorted(arr, reverse=True)

        # If pass_count is greater than or equal to the length of the array,
        # it means all elements can pass, so we return the smallest element.
        if pass_count >= len(arr):
            return sorted_arr[-1] if sorted_arr else 0.0

        # The element at index pass_count-1 is the smallest number such
        # that at most pass_count elements are greater than or equal to it
        return sorted_arr[pass_count - 1]

    def validate_threshold(self, arr, threshold):
        passed_n = sum(1 for x in arr if x >= threshold) if arr else 0
        self.logger.info(f'Passed values: {passed_n}/{len(arr)}')
