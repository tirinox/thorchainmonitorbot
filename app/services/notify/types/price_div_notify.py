from localization.manager import BaseLocalization
from services.lib.delegates import INotified
from services.lib.config import SubConfig
from services.lib.cooldown import CooldownBiTrigger
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.price import RuneMarketInfo
from services.models.time_series import TimeSeries


class PriceDivergenceNotifier(INotified):
    MAX_POINTS = 20000

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        cfg: SubConfig = deps.cfg.price.divergence

        self.min_percent = cfg.as_float('public.min_percent', 2.0)
        self.max_percent = cfg.as_float('public.max_percent', 5.0)

        self.main_cd = parse_timespan_to_seconds(cfg.as_str('cooldown', '6h'))

        self._cd_bitrig = CooldownBiTrigger(deps.db, 'PriceDivergence', self.main_cd, default=False)
        self.time_series = TimeSeries('PriceDivergence', deps.db)

    async def on_data(self, sender, rune_market_info: RuneMarketInfo):
        bep2_price, native_price = rune_market_info.cex_price, rune_market_info.pool_rune_price

        if native_price == 0:
            return

        div_p = rune_market_info.divergence_percent

        if div_p < self.min_percent:
            if await self._cd_bitrig.turn_off():
                await self._notify(rune_market_info, is_low=True)
        elif div_p > self.max_percent:
            if await self._cd_bitrig.turn_on():
                await self._notify(rune_market_info, is_low=False)

        await self.time_series.add(
            abs_delta=(bep2_price - native_price),
            rel_delta=div_p
        )
        await self.time_series.trim_oldest(self.MAX_POINTS)

    async def _notify(self, rune_market_info: RuneMarketInfo, is_low):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_price_divergence,
            rune_market_info,
            is_low
        )
