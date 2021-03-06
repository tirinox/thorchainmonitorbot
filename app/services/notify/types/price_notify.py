import asyncio
import logging
import time

from localization import BaseLocalization
from services.dialog.picture.price_picture import price_graph_from_db
from services.jobs.fetch.base import INotified
from services.lib.constants import RUNE_SYMBOL_POOL
from services.lib.cooldown import CooldownSingle
from services.lib.date_utils import MINUTE, HOUR, DAY, parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.money import pretty_money, calc_percent_change
from services.lib.texts import MessageType, BoardMessage
from services.lib.utils import make_stickers_iterator
from services.models.price import RuneMarketInfo, PriceReport, PriceATH
from services.models.time_series import PriceTimeSeries


class PriceNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cd = CooldownSingle(deps.db)
        cfg = deps.cfg.price
        self.global_cd = parse_timespan_to_seconds(cfg.global_cd)
        self.change_cd = parse_timespan_to_seconds(cfg.change_cd)
        self.percent_change_threshold = cfg.percent_change_threshold
        self.time_series = PriceTimeSeries(RUNE_SYMBOL_POOL, deps.db)

        self.ath_stickers = cfg.ath.stickers
        self.ath_sticker_iter = make_stickers_iterator(self.ath_stickers)

        self.ath_cooldown = parse_timespan_to_seconds(cfg.ath.cooldown)
        self.price_graph_period = parse_timespan_to_seconds(cfg.price_graph.default_period)

    async def on_data(self, sender, fprice: RuneMarketInfo):
        # fprice.pool_rune_price = 21.98  # fixme: debug! for ATH
        if not await self.handle_ath(fprice):
            await self.handle_new_price(fprice)

    # -----

    ATH_KEY = 'runeATH'
    CD_KEY_PRICE_NOTIFIED = 'price_notified'
    CD_KEY_PRICE_RISE_NOTIFIED = 'price_notified_rise'
    CD_KEY_PRICE_FALL_NOTIFIED = 'price_notified_fall'
    CD_KEY_ATH_NOTIFIED = 'ath_notified'

    async def historical_get_triplet(self):
        price_1h, price_24h, price_7d = await asyncio.gather(
            self.time_series.select_average_ago(HOUR, tolerance=MINUTE * 7),
            self.time_series.select_average_ago(DAY, tolerance=MINUTE * 40),
            self.time_series.select_average_ago(DAY * 7, tolerance=HOUR * 2)
        )
        return price_1h, price_24h, price_7d

    async def send_ath_sticker(self):
        sticker = next(self.ath_sticker_iter)
        user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)
        await self.deps.broadcaster.broadcast(user_lang_map.keys(), sticker, message_type=MessageType.STICKER)

    async def do_notify_price_table(self, market_info, hist_prices, ath, last_ath=None):
        await self.cd.do(self.CD_KEY_PRICE_NOTIFIED)

        btc_price = self.deps.price_holder.btc_per_rune
        report = PriceReport(*hist_prices, market_info, last_ath, btc_price)

        user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)

        async def price_graph_gen(chat_id):
            loc: BaseLocalization = user_lang_map[chat_id]
            graph = await price_graph_from_db(self.deps.db, loc, self.price_graph_period)
            caption = loc.notification_text_price_update(report, ath, is_halted=bool(self.deps.halted_chains))
            return BoardMessage.make_photo(graph, caption=caption)

        if ath:
            await self.send_ath_sticker()

        await self.deps.broadcaster.broadcast(user_lang_map, price_graph_gen)

    async def handle_new_price(self, market_info: RuneMarketInfo):
        hist_prices = await self.historical_get_triplet()
        price = market_info.pool_rune_price

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
            await self.do_notify_price_table(market_info, hist_prices, ath=False)

    async def get_prev_ath(self) -> PriceATH:
        try:
            await self.deps.db.get_redis()
            ath_str = await self.deps.db.redis.get(self.ATH_KEY)
            if ath_str is None:
                return PriceATH()
            else:
                return PriceATH.from_json(ath_str)
        except (TypeError, ValueError, AttributeError):
            return PriceATH()

    async def reset_ath(self):
        await self.deps.db.redis.delete(self.ATH_KEY)

    async def update_ath(self, ath: PriceATH):
        if ath.ath_price > 0:
            await self.deps.db.get_redis()
            await self.deps.db.redis.set(self.ATH_KEY, ath.as_json_string)

    async def handle_ath(self, market_info: RuneMarketInfo):
        last_ath = await self.get_prev_ath()
        price = market_info.pool_rune_price

        if last_ath.is_new_ath(price):
            await self.update_ath(PriceATH(
                int(time.time()), price
            ))

            if await self.cd.can_do(self.CD_KEY_ATH_NOTIFIED, self.ath_cooldown):
                await self.cd.do(self.CD_KEY_ATH_NOTIFIED)
                await self.cd.do(self.CD_KEY_PRICE_RISE_NOTIFIED)  # prevent 2 notifications

                hist_prices = await self.historical_get_triplet()
                await self.do_notify_price_table(market_info, hist_prices, ath=True, last_ath=last_ath)
                return True

        return False

    # ----- PRICE PEAK DETECTOR

    async def price_peak(self, period_sec=HOUR):
        points = await self.time_series.get_last_values(period_sec, tolerance_sec=period_sec / 100, with_ts=True)
        # [ (ts, price) ]

        # ----- ATH DETECTOR ----
        # todo:
        # 1. take a window on the timeline (e.g. 1 HOUR till now)
        # 2. detect if it has ATH inside
        # 3. make sure that after ATH price is less than it for some time (10min)
        # 4. signal
