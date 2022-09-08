import asyncio

from localization.manager import BaseLocalization
from services.dialog.picture.price_picture import price_graph_from_db
from services.lib.constants import RUNE_SYMBOL_POOL
from services.lib.cooldown import Cooldown
from services.lib.date_utils import MINUTE, HOUR, DAY, parse_timespan_to_seconds, now_ts
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.money import pretty_money, calc_percent_change
from services.lib.utils import make_stickers_iterator, class_logger
from services.models.price import RuneMarketInfo, PriceReport, PriceATH
from services.models.time_series import PriceTimeSeries
from services.notify.channel import MessageType, BoardMessage


class PriceNotifier(INotified):
    ATH_KEY = 'runeATH'
    CD_KEY_PRICE_NOTIFIED = 'price_notified'
    CD_KEY_PRICE_RISE_NOTIFIED = 'price_notified_rise'
    CD_KEY_PRICE_FALL_NOTIFIED = 'price_notified_fall'
    CD_KEY_ATH_NOTIFIED = 'ath_notified'

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

        cfg = deps.cfg.price
        self.percent_change_threshold = cfg.percent_change_threshold
        self._global_cd = parse_timespan_to_seconds(cfg.global_cd)
        self._change_cd = parse_timespan_to_seconds(cfg.change_cd)
        self._ath_cd = parse_timespan_to_seconds(cfg.ath.cooldown)

        self._cd_price_regular = Cooldown(deps.db, self.CD_KEY_PRICE_NOTIFIED, self._global_cd)
        self._cd_price_rise = Cooldown(deps.db, self.CD_KEY_PRICE_RISE_NOTIFIED, self._change_cd)
        self._cd_price_fall = Cooldown(deps.db, self.CD_KEY_PRICE_FALL_NOTIFIED, self._change_cd)
        self._cd_price_ath = Cooldown(deps.db, self.CD_KEY_ATH_NOTIFIED, self._ath_cd)

        self.time_series = PriceTimeSeries(RUNE_SYMBOL_POOL, deps.db)

        self.ath_stickers = cfg.ath.stickers
        self.ath_sticker_iter = make_stickers_iterator(self.ath_stickers)

        self.price_graph_period = parse_timespan_to_seconds(cfg.price_graph.default_period)

    async def on_data(self, sender, market_info: RuneMarketInfo):
        # market_info.pool_rune_price = 50.98  # fixme: debug! for ATH

        if not await self.handle_ath(market_info):
            await self.handle_new_price(market_info)

    # -----

    async def historical_get_triplet(self):
        price_1h, price_24h, price_7d = await asyncio.gather(
            self.time_series.select_average_ago(HOUR, tolerance=MINUTE * 7),
            self.time_series.select_average_ago(DAY, tolerance=MINUTE * 40),
            self.time_series.select_average_ago(DAY * 7, tolerance=HOUR * 2)
        )
        return price_1h, price_24h, price_7d

    async def send_ath_sticker(self):
        sticker = next(self.ath_sticker_iter)
        await self.deps.broadcaster.notify_preconfigured_channels(BoardMessage(sticker, MessageType.STICKER))

    async def do_notify_price_table(self, market_info, hist_prices, ath, last_ath=None):
        btc_price = self.deps.price_holder.btc_per_rune
        report = PriceReport(*hist_prices, market_info, last_ath, btc_price)

        async def price_graph_gen(loc: BaseLocalization):
            graph, graph_name = await price_graph_from_db(self.deps, loc, self.price_graph_period)
            caption = loc.notification_text_price_update(report, ath, halted_chains=self.deps.halted_chains)
            return BoardMessage.make_photo(graph, caption=caption, photo_file_name=graph_name)

        if ath:
            await self.send_ath_sticker()

        await self.deps.broadcaster.notify_preconfigured_channels(price_graph_gen)

    async def handle_new_price(self, market_info: RuneMarketInfo):
        hist_prices = await self.historical_get_triplet()
        price = market_info.pool_rune_price

        price_1h = hist_prices[0]
        send_it = False
        if price_1h:
            percent_change = calc_percent_change(price_1h, price)

            if abs(percent_change) >= self.percent_change_threshold:  # significant price change
                if percent_change > 0 and (await self._cd_price_rise.can_do()):
                    self.logger.info(f'price rise {pretty_money(percent_change)} %')
                    await self._cd_price_rise.do()
                    send_it = True
                elif percent_change < 0 and (await self._cd_price_fall.can_do()):
                    self.logger.info(f'price fall {pretty_money(percent_change)} %')
                    await self._cd_price_fall.do()
                    send_it = True

        if not send_it and await self._cd_price_regular.can_do():
            self.logger.info('no price change but it is long time elapsed (global cd), so notify anyway')
            send_it = True

        if send_it:
            await self._cd_price_regular.do()
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
                int(now_ts()), price
            ))

            if await self._cd_price_ath.can_do():
                await self._cd_price_ath.do()
                await self._cd_price_rise.do()  # prevent 2 notifications

                hist_prices = await self.historical_get_triplet()
                await self._cd_price_regular.do()
                await self.do_notify_price_table(market_info, hist_prices, ath=True, last_ath=last_ath)
                return True

        return False
