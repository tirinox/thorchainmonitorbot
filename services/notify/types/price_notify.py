import logging

from localization import LocalizationManager
from services.config import Config
from services.cooldown import CooldownTracker
from services.db import DB
from services.fetch.base import INotified
from services.fetch.fair_price import RuneFairPrice
from services.fetch.pool_price import RUNE_SYMBOL
from services.models.time_series import PriceTimeSeries
from services.notify.broadcast import Broadcaster
from services.utils import parse_timespan_to_seconds, HOUR, MINUTE, DAY

EMOJI_SCALE = [
    # negative
    (-50, '💥'), (-35, '👺'), (-25, '😱'), (-20, '😨'), (-15, '🥵'), (-10, '😰'), (-5, '😢'), (-3, '😥'), (-2, '😔'),
    (-1, '😑'), (0, '😕'),
    # positive
    (1, '😏'), (2, '😄'), (3, '😀'), (5, '🤗'), (10, '🍻'), (15, '🎉'), (20, '💸'), (25, '🔥'), (35, '🌙'), (50, '🌗'),
    (65, '🌕'), (80, '⭐'), (100, '✨'), (10000000, '⚡')
]

REAL_REGISTERED_ATH = 1.18  # BUSD / Rune


def emoji_for_percent_change(pc):
    for threshold, emoji in EMOJI_SCALE:
        if pc <= threshold:
            return emoji
    return EMOJI_SCALE[-1]  # last one


class PriceNotification(INotified):
    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, loc_man: LocalizationManager):
        self.logger = logging.getLogger('PriceNotification')
        self.broadcaster = broadcaster
        self.loc_man = loc_man
        self.cfg = cfg
        self.db = db
        self.cd = CooldownTracker(db)
        self.global_cd = parse_timespan_to_seconds(cfg.price.global_cd)
        self.percent_change = cfg.price.percent_change
        self.time_series = PriceTimeSeries(RUNE_SYMBOL, cfg, db)

    async def handle_ath(self, price):
        return False

    CD_KEY_PRICE_NOTIFIED = 'price_notified'
    CD_KEY_ATH_NOTIFIED = 'ath_notified'

    async def do_notify_price_table(self, price, fair_price):
        ...

    async def handle_new_price(self, price, fair_price):
        price_1h = await self.time_series.select_average_ago(HOUR, tolerance=MINUTE * 5)
        price_24h = await self.time_series.select_average_ago(DAY, tolerance=MINUTE * 30)
        price_7d = await self.time_series.select_average_ago(DAY * 7, tolerance=HOUR * 1)


        if await self.cd.can_do(self.CD_KEY_ATH_NOTIFIED, self.global_cd):
            await self.do_notify_price_table(price, fair_price)

    async def on_data(self, data):
        price, fair_price = data
        fair_price: RuneFairPrice

        if not await self.handle_ath(price):
            await self.handle_new_price(price, fair_price)

    async def on_error(self, e):
        return await super().on_error(e)
