import datetime

from aiohttp import ClientSession

from lib.logs import WithLogger
from models.key_stats_model import AffiliateCollectors

FS_AFFILIATES_API_URL = "https://flipsidecrypto.xyz/api/v1/queries/cebb9137-b58f-452d-a30a-6990a8e8fdc8/data/latest"


class FlipsideConnector(WithLogger):
    def __init__(self, session: ClientSession, emergency):
        super().__init__()
        self.session = session
        self.emergency = emergency

    async def get_affiliates_from_flipside(self):
        async with self.session.get(FS_AFFILIATES_API_URL) as resp:
            if resp.status == 200:
                j = await resp.json()
                aff_collectors = [AffiliateCollectors.from_json(item) for item in j]
                aff_collectors.sort(key=lambda item: item.date, reverse=True)

                if not aff_collectors:
                    self.logger.error(f'No data loaded')
                    if self.emergency:
                        self.emergency.report('WeeklyStats',
                                              'No data loaded',
                                              url=FS_AFFILIATES_API_URL)
                    raise IOError('No data from Flipside')

                max_date = aff_collectors[0].date
                if max_date - datetime.datetime.now() > datetime.timedelta(days=2):
                    self.logger.error("FS data is too old")
                    if self.emergency:
                        self.emergency.report('WeeklyStats', 'FS Aff data is too old',
                                              date=max_date, url=FS_AFFILIATES_API_URL)
                    raise IOError('Flipside returned outdated rows')

                return aff_collectors
