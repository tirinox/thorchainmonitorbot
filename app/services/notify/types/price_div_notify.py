from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.config import SubConfig
from services.lib.cooldown import CooldownBiTrigger
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.price import RuneMarketInfo


class PriceDivergenceNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        cfg: SubConfig = deps.cfg.price.divergence
        # self.global_cd = parse_timespan_to_seconds(cfg.global_cd)

        self.normal_div = cfg.as_float('normal_is_less', 2.0)
        self.div_steps = cfg.get_pure('div_steps', default=[5, 10, 20])
        self.div_steps = [float(x) for x in self.div_steps]

        self.main_cd = parse_timespan_to_seconds(cfg.as_float('cooldown', '6h'))

        self._cd_bitrig = CooldownBiTrigger(deps.db, 'PriceDivergence', self.main_cd, default=False)

    async def on_data(self, sender, rune_market_info: RuneMarketInfo):
        # rune_market_info.pool_rune_price = 11.66  # fixme: debug

        bep2_price, native_price = rune_market_info.cex_price, rune_market_info.pool_rune_price

        if native_price == 0:
            return

        div_p = 100.0 * abs(1.0 - bep2_price / native_price)

        if div_p < self.normal_div:
            if await self._cd_bitrig.turn_off():
                await self._notify(rune_market_info, normal=True)
        elif div_p > min(*self.div_steps):
            if await self._cd_bitrig.turn_on():
                await self._notify(rune_market_info, normal=False)

    async def _notify(self, rune_market_info: RuneMarketInfo, normal):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_price_divergence,
            rune_market_info,
            normal,
        )
