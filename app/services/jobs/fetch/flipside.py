from collections import defaultdict
from datetime import datetime

import aiohttp

from services.lib.date_utils import now_ts, DAY, discard_time
from services.lib.utils import WithLogger


class FSList(dict):
    KEY_TS = '__ts'

    @staticmethod
    def parse_date(string_date):
        return datetime.strptime(string_date, '%Y-%m-%d')

    @staticmethod
    def get_date(obj: dict):
        if obj:
            return obj.get('DAY') or obj.get('DATE')

    def __init__(self, data):
        super().__init__()
        self.latest_timestamp = 0
        self.latest_date = datetime(1991, 1, 1)

        if not data:
            return

        grouped_by = defaultdict(list)
        for item in data:
            if str_date := self.get_date(item):
                date = self.parse_date(str_date)
                ts = item[self.KEY_TS] = date.timestamp()
                self.latest_date = max(self.latest_date, date)
                self.latest_timestamp = max(self.latest_timestamp, ts)
                grouped_by[date].append(item)
        self.update(grouped_by)

    @property
    def most_recent(self):
        return self[self.latest_date]

    @property
    def most_recent_one(self):
        return self.most_recent[0]

    def get_data_days_ago(self, days, single=False):
        then = datetime.fromtimestamp(now_ts() - days * DAY)
        then = discard_time(then)
        data_then = self.get(then)
        if single:
            return data_then[0] if data_then else None
        else:
            return data_then or []

    @property
    def min_age(self):
        return now_ts() - self.latest_timestamp


class FlipSideConnector(WithLogger):
    def __init__(self, session: aiohttp.ClientSession):
        super().__init__()
        self.session = session

    async def request(self, url):
        self.logger.info(f'Getting "{url}"...')
        async with self.session.get(url) as resp:
            data = await resp.json()
            if hasattr(data, '__len__'):
                self.logger.info(f'"{url}" returned total {len(data)} objects')
            elif not data:
                self.logger.error(f'No data for URL: "{url}"')
            else:
                self.logger.info(f'"{url}" returned object of type "{type(data)}"')
            return data

    async def request_daily_series(self, url):
        data = await self.request(url)
        return FSList(data)
