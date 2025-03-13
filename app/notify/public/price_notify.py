from comm.picture.price_picture import VOLUME_N_POINTS
from jobs.price_recorder import PriceRecorder
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds, now_ts, HOUR
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.money import pretty_money, calc_percent_change
from lib.utils import make_stickers_iterator, WithLogger
from models.price import RuneMarketInfo, AlertPrice, PriceATH


class PriceNotifier(INotified, WithDelegates, WithLogger):
    ATH_KEY = 'runeATH'
    CD_KEY_PRICE_NOTIFIED = 'price_notified'
    CD_KEY_PRICE_RISE_NOTIFIED = 'price_notified_rise'
    CD_KEY_PRICE_FALL_NOTIFIED = 'price_notified_fall'
    CD_KEY_ATH_NOTIFIED = 'ath_notified'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        cfg = deps.cfg.price
        self.percent_change_threshold = cfg.percent_change_threshold
        self._global_cd = parse_timespan_to_seconds(cfg.global_cd)
        self._change_cd = parse_timespan_to_seconds(cfg.change_cd)
        self._ath_cd = parse_timespan_to_seconds(cfg.ath.cooldown)

        self._cd_price_regular = Cooldown(deps.db, self.CD_KEY_PRICE_NOTIFIED, self._global_cd)
        self._cd_price_rise = Cooldown(deps.db, self.CD_KEY_PRICE_RISE_NOTIFIED, self._change_cd)
        self._cd_price_fall = Cooldown(deps.db, self.CD_KEY_PRICE_FALL_NOTIFIED, self._change_cd)
        self._cd_price_ath = Cooldown(deps.db, self.CD_KEY_ATH_NOTIFIED, self._ath_cd)

        self.price_recorder = PriceRecorder(deps.db)

        self.ath_stickers = cfg.ath.stickers.as_list()
        self.ath_sticker_iter = make_stickers_iterator(self.ath_stickers)

        self.price_graph_period = parse_timespan_to_seconds(cfg.price_graph.default_period)

    async def on_data(self, sender, market_info: RuneMarketInfo):
        # market_info.pool_rune_price = 50.98  # fixme: debug! for ATH

        if not await self.handle_ath(market_info):
            await self.handle_new_price(market_info)

    # -----

    async def get_historical_price_dict(self):
        """
        Returns 5 pool prices: price_1h, price_24h, price_7d, price_30d, price_1y
        """
        return await self.price_recorder.get_historical_price_dict()

    def _next_ath_sticker(self):
        try:
            return next(self.ath_sticker_iter)
        except (StopIteration, TypeError, ValueError):
            return ''

    async def make_event(self, market_info, ath, last_ath=None):
        btc_per_rune = self.deps.price_holder.btc_per_rune

        hist_prices = await self.get_historical_price_dict()
        pool_prices, cex_prices, det_prices = await self.price_recorder.get_prices(self.price_graph_period)
        volumes = await self.deps.volume_recorder.get_data_range_ago_n(self.price_graph_period, n=VOLUME_N_POINTS)

        return AlertPrice(
            hist_prices=hist_prices,
            pool_prices=pool_prices,
            cex_prices=cex_prices,
            det_prices=det_prices,
            volumes=volumes,
            market_info=market_info,
            last_ath=last_ath,
            btc_pool_rune_price=btc_per_rune,
            is_ath=ath,
            ath_sticker=self._next_ath_sticker(),
            chain_state=self.deps.chain_info.state_list,
            price_graph_period=self.price_graph_period,
        )

    async def do_notify_price_table(self, market_info, ath, last_ath=None):
        price_alert = await self.make_event(market_info, ath, last_ath)
        await self.pass_data_to_listeners(price_alert)

    async def handle_new_price(self, market_info: RuneMarketInfo):
        hist_prices = await self.get_historical_price_dict()
        price = market_info.pool_rune_price

        price_1h = hist_prices[HOUR]
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
            await self.do_notify_price_table(market_info, ath=False)

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

                await self._cd_price_regular.do()
                await self.do_notify_price_table(market_info, ath=True, last_ath=last_ath)
                return True

        return False
