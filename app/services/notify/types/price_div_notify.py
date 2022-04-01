from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.cooldown import CooldownSingle
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.price import RuneMarketInfo


class PriceDivergenceNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.cd = CooldownSingle(deps.db)
        cfg = deps.cfg.price.divergence
        # self.global_cd = parse_timespan_to_seconds(cfg.global_cd)

    async def on_data(self, sender, rune_market_info: RuneMarketInfo):
        bep2_price, native_price = rune_market_info.cex_price, rune_market_info.pool_rune_price

        # todo: fix
        await self._notify(rune_market_info)

    async def _notify(self, rune_market_info: RuneMarketInfo):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_price_divergence,
            rune_market_info,
            True,  # normal?
        )
