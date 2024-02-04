import asyncio
import os.path
from collections import defaultdict
from datetime import datetime, timedelta

import aiohttp
from flipside import Flipside
from flipside.flipside import API_BASE_URL

from services.lib.date_utils import now_ts, DAY, discard_time, HOUR, MINUTE, date_parse_rfc_z_no_ms
from services.lib.utils import WithLogger

KEY_TS = '__ts'
KEY_DATETIME = '__dt'


class FSList(dict):
    @staticmethod
    def parse_date(string_date):
        try:
            return date_parse_rfc_z_no_ms(string_date)
        except ValueError:
            pass

        try:
            return datetime.strptime(string_date, '%Y-%m-%d') if string_date else None
        except ValueError:
            return datetime.strptime(string_date, '%Y-%m-%d %H:%M:%S.%f')

    @staticmethod
    def get_date(obj: dict):
        if obj:
            return obj.get('day') or obj.get('date') or obj.get('DAY') or obj.get('DATE')

    @classmethod
    def from_server(cls, data, max_days=0):
        self = cls()

        if not data:
            return

        grouped_by = defaultdict(list)
        for item in data:
            if str_date := self.get_date(item):
                date = item[KEY_DATETIME] = self.parse_date(str_date)
                item[KEY_TS] = date.timestamp()
                grouped_by[date].append(item)

            if max_days and len(grouped_by) >= max_days:
                break

        self.update(grouped_by)
        return self

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.klass = dict

    @property
    def latest_date(self):
        return max(self.keys()) if self else datetime(1990, 1, 1)

    @property
    def most_recent(self):
        return self[self.latest_date]

    @property
    def most_recent_one(self):
        return self.most_recent[0]

    def get_data_from_day(self, dt, klass=None):
        then = discard_time(dt)
        data_then = self.get(then)
        if data_then:
            return data_then.get(klass) if klass else data_then

    def get_data_days_ago(self, days, klass=None):
        then = datetime.fromtimestamp(now_ts() - days * DAY)
        return self.get_data_from_day(then, klass)

    def get_prev_and_curr(self, days, klass=None):
        last = self.latest_date
        curr = self.get_data_from_day(last, klass)
        prev = self.get_data_from_day(last - timedelta(days=days), klass)
        return prev, curr

    def get_range(self, days, klass=None, start_dt=None):
        accum = []
        dt = start_dt or self.latest_date
        for _ in range(days):
            data = self.get_data_from_day(dt, klass)
            if data:
                accum.append(data)
            dt -= timedelta(days=1)
        return accum

    def get_current_and_previous_range(self, days, klass=None):
        curr_fees_tally = self.get_range(days, klass=klass)
        prev_week_end = self.latest_date - timedelta(days=days)
        prev_fees_tally = self.get_range(days, klass=klass, start_dt=prev_week_end)
        return curr_fees_tally, prev_fees_tally

    @property
    def min_age(self):
        return now_ts() - self.latest_date.timestamp()

    def transform_from_json(self, klass, f='from_json'):
        loader = getattr(klass, f)
        result = FSList([
            (k, [
                loader(piece) for piece in v
            ]) for k, v in self.items()
        ])
        result.klass = klass
        return result

    @property
    def all_dates_set(self):
        return set(self.keys())

    def all_pieces_of_type_to_date(self, date, klass):
        return [piece for piece in self.get(date, []) if isinstance(piece, klass)]

    @classmethod
    def combine(cls, *lists):
        results = cls()
        for fs_list in lists:
            fs_list: FSList
            for date, v in fs_list.items():
                if date not in results:
                    results[date] = defaultdict(list)
                results[date][fs_list.klass].extend(v)
        return results

    @staticmethod
    def has_classes(row, class_list):
        return all(klass in row for klass in class_list)

    def remove_incomplete_rows(self, class_list) -> 'FSList':
        result = FSList(self)
        if not class_list:
            return result

        for date in sorted(result.keys(), reverse=True):
            row = result[date]
            if not result.has_classes(row, class_list):
                del result[date]
        return result

    def sum_attribute(self, attribute: str, max_days=-1):
        summed = 0
        for day_no, date in enumerate(sorted(self.values(), reverse=True)):
            if 0 < max_days <= day_no:
                break
            for item in self[date]:
                summed += getattr(item, attribute)
        return summed


class FlipSideConnector(WithLogger):
    def __init__(self, session: aiohttp.ClientSession, flipside_api_key: str,
                 flipside_api_url: str = API_BASE_URL):
        super().__init__()
        self.session = session
        self.flipside = Flipside(flipside_api_key, flipside_api_url)
        self.max_cache_age = 24 * HOUR

    async def request(self, url):
        self.logger.info(f'Getting "{url}"...')
        async with self.session.get(url) as resp:
            data = await resp.json()
            if not data:
                self.logger.error(f'No data for URL: "{url}"')
            elif not hasattr(data, '__len__'):
                self.logger.info(f'"{url}" returned object of type "{type(data)}" (no __len__)')
            return data

    async def request_daily_series(self, url, max_days=0):
        data = await self.request(url)
        fs_list = FSList.from_server(data, max_days)
        self.logger.info(f'"{url}" returned total {len(data)} objects; latest date is {fs_list.latest_date}')
        return fs_list

    def _direct_sql_query_sync(self, sql):
        return self.flipside.query(sql, max_age_minutes=self.max_cache_age / MINUTE)

    async def direct_sql_query(self, sql):
        return await asyncio.get_event_loop().run_in_executor(None, self._direct_sql_query_sync, sql)

    async def direct_sql_file_query(self, filename):
        sql = self.load_sql(filename)
        return await self.direct_sql_query(sql)

    BASE_PATH = './services/jobs/fetch/flipside/'

    @classmethod
    def load_sql(cls, filename):
        path = os.path.join(cls.BASE_PATH, filename)
        with open(path) as f:
            return f.read()

    async def request_daily_series_sql_file(self, filename, max_days=0):
        sql = self.load_sql(filename)
        data = await self.direct_sql_query(sql)
        if data.error:
            raise Exception(f"Failed to load Flipside query for {filename}: {data.error}")

        records = data.records
        fs_list = FSList.from_server(records, max_days)

        self.logger.info(f'"{filename}" returned total {len(records)} objects; latest date is {fs_list.latest_date}')
        return fs_list
