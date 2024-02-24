import asyncio
import os.path
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict

import aiohttp
from flipside import Flipside
from flipside.flipside import API_BASE_URL
from pydantic import ValidationError

from services.lib.date_utils import now_ts, DAY, discard_time, HOUR, MINUTE, date_parse_rfc_z_no_ms
from services.lib.utils import WithLogger

KEY_TS = '__ts'
KEY_DATETIME = '__dt'


@dataclass
class FSList:
    # Date => [List of FS_XXx]
    data: Dict[datetime, List] = field(default_factory=lambda: defaultdict(list))

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

        self.data.update(grouped_by)
        return self

    @classmethod
    def from_server_v2(cls, data, klass):
        self = cls()
        if not data:
            return self

        columns = data['result']['columnNames']

        for row in data['result']['rows']:
            # combine columns and row into a dict
            item = {}
            for column, value in zip(columns, row):
                item[column] = value

            # parse date
            day_value = self.get_date(item)
            date = item[KEY_DATETIME] = self.parse_date(day_value)
            item[KEY_TS] = date.timestamp()

            # create object
            item_obj = klass.from_json(item)

            # add to the list
            self.data[date].append(item_obj)

        return self

    @property
    def latest_date(self):
        return max(self.data.keys()) if self else datetime(1990, 1, 1)

    @property
    def most_recent(self):
        return self.data[self.latest_date]

    @property
    def most_recent_one(self):
        return self.most_recent[0]

    def get_data_from_day(self, dt, klass=None):
        then = discard_time(dt)
        data_then = self.data.get(then)
        if data_then:
            return [d for d in data_then if not klass or isinstance(d, klass)]

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
        data = {k: [loader(piece) for piece in v] for k, v in self.data.items()}
        result = FSList()
        result.data = defaultdict(list, data)
        return result

    @property
    def all_dates_set(self):
        return set(self.data.keys())

    def all_pieces_of_type_to_date(self, date, klass):
        return [piece for piece in self.data.get(date, []) if isinstance(piece, klass)]

    @classmethod
    def combine(cls, *lists):
        results = cls()
        for fs_list in lists:
            fs_list: FSList
            for date, v in fs_list.data.items():
                results.data[date].extend(v)
        return results

    @staticmethod
    def has_classes(row, class_list):
        return all(klass in row for klass in class_list)

    def remove_incomplete_rows(self, class_list) -> 'FSList':
        result = FSList()
        result.data = self.data.copy()

        if not class_list:
            return result

        for date in sorted(result.data.keys(), reverse=True):
            row = result.data[date]
            if not result.has_classes(row, class_list):
                del result.data[date]
        return result


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
        try:
            sql = self.load_sql(filename)
            data = await self.direct_sql_query(sql)
            if data.error:
                raise Exception(f"Failed to load Flipside query for {filename}: {data.error}")

            records = data.records
            fs_list = FSList.from_server(records, max_days)

            self.logger.info(
                f'"{filename}" returned total {len(records)} objects; latest date is {fs_list.latest_date}')
            return fs_list
        except ValidationError:
            self.logger.exception(f'Failed to load Flipside query for {filename}')
            return None

    async def request_daily_series_v2(self, url, klass):
        data = await self.request(url)
        if not data:
            self.logger.error(f'No data for URL: "{url}"')
            return

        return FSList.from_server_v2(data, klass)
