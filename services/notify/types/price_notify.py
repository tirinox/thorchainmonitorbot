import asyncio
import logging

from localization import LocalizationManager, BaseLocalization
from services.config import Config
from services.cooldown import CooldownTracker
from services.db import DB
from services.fetch.base import INotified
from services.models.price import RuneFairPrice, PriceReport
from services.models.time_series import PriceTimeSeries, RUNE_SYMBOL
from services.notify.broadcast import Broadcaster, telegram_chats_from_config
from services.utils import parse_timespan_to_seconds, HOUR, MINUTE, DAY, calc_percent_change, pretty_money

REAL_REGISTERED_ATH = 1.18  # BUSD / Rune


class PriceNotifier(INotified):
    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, loc_man: LocalizationManager):
        self.logger = logging.getLogger('PriceNotification')
        self.broadcaster = broadcaster
        self.loc_man = loc_man
        self.cfg = cfg
        self.db = db
        self.cd = CooldownTracker(db)
        self.global_cd = parse_timespan_to_seconds(cfg.price.global_cd)
        self.change_cd = parse_timespan_to_seconds(cfg.price.change_cd)
        self.percent_change_threshold = cfg.price.percent_change_threshold
        self.time_series = PriceTimeSeries(RUNE_SYMBOL, db)

    CD_KEY_PRICE_NOTIFIED = 'price_notified'
    CD_KEY_PRICE_RISE_NOTIFIED = 'price_notified_rise'
    CD_KEY_PRICE_FALL_NOTIFIED = 'price_notified_fall'
    CD_KEY_ATH_NOTIFIED = 'ath_notified'

    async def historical_get_triplet(self):
        price_1h, price_24h, price_7d = await asyncio.gather(
            self.time_series.select_average_ago(HOUR, tolerance=MINUTE * 5),
            self.time_series.select_average_ago(DAY, tolerance=MINUTE * 30),
            self.time_series.select_average_ago(DAY * 7, tolerance=HOUR * 1)
        )
        return price_1h, price_24h, price_7d

    async def do_notify_price_table(self, price, fair_price, hist_prices):
        await self.cd.do(self.CD_KEY_PRICE_NOTIFIED)

        user_lang_map = telegram_chats_from_config(self.cfg, self.loc_man)

        async def message_gen(chat_id):
            loc: BaseLocalization = user_lang_map[chat_id]
            return loc.price_change(PriceReport(
                price, *hist_prices, fair_price
            ))

        await self.broadcaster.broadcast(user_lang_map.keys(), message_gen)

    async def handle_new_price(self, price, fair_price: RuneFairPrice):
        hist_prices = await self.historical_get_triplet()

        price_1h = hist_prices[0]
        send_it = False
        if price_1h:
            percent_change = calc_percent_change(price_1h, price)

            if abs(percent_change) >= self.percent_change_threshold:  # significant price change
                if percent_change > 0 and (await self.cd.can_do(self.CD_KEY_PRICE_RISE_NOTIFIED, self.change_cd)):
                    self.logger.info(f'price rise {pretty_money(percent_change)} %')
                    await self.cd.do(self.CD_KEY_PRICE_RISE_NOTIFIED)
                    send_it = True
                elif percent_change < 0 and (await self.cd.can_do(self.CD_KEY_PRICE_FALL_NOTIFIED, self.change_cd)):
                    self.logger.info(f'price fall {pretty_money(percent_change)} %')
                    await self.cd.do(self.CD_KEY_PRICE_FALL_NOTIFIED)
                    send_it = True

        if not send_it and await self.cd.can_do(self.CD_KEY_PRICE_NOTIFIED, self.global_cd):
            self.logger.info('no price change but it is long time elapsed (global cd), so notify anyway')
            send_it = True

        if send_it:
            await self.do_notify_price_table(price, fair_price, hist_prices)

    async def handle_ath(self, price):
        return False

    async def on_data(self, data):
        price, fair_price = data
        fair_price: RuneFairPrice

        # price = 1.2  # debug

        await self.handle_new_price(price, fair_price)

        # todo: uncomment
        # if not await self.handle_ath(price):
        #     await self.handle_new_price(price, fair_price)

    async def on_error(self, e):
        return await super().on_error(e)
