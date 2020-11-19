import logging

from localization import LocalizationManager
from services.fetch.base import INotified
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.notify.broadcast import Broadcaster


class PoolChurnNotifier(INotified):
    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, loc_man: LocalizationManager):
        self.logger = logging.getLogger('CapFetcherNotification')
        self.broadcaster = broadcaster
        self.loc_man = loc_man
        self.cfg = cfg
        self.db = db
        self.old_pool_data = {}

    async def on_data(self, sender: PoolPriceFetcher, fair_price):
        pim = sender.price_holder.pool_info_map
        if not pim:
            self.logger.warning('pool_info_map not filled yet..')
            return

        if self.old_pool_data:
            # todo: persist old_pool_data in DB!
            await self.compare_pool_sets()  # compare starting w 2nd iteration

        self.old_pool_data = pim

    async def compare_pool_sets(self):
        ...
