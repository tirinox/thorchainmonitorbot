from lib.config import SubConfig
from lib.cooldown import CooldownBiTrigger
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.price import RuneMarketInfo, AlertPriceDiverge
from models.time_series import TimeSeries


class PriceDivergenceNotifier(INotified, WithLogger, WithDelegates):
    MAX_POINTS = 20000

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        cfg: SubConfig = deps.cfg.price.divergence

        self.min_percent = cfg.as_float('public.min_percent', 2.0)
        self.max_percent = cfg.as_float('public.max_percent', 5.0)

        self.main_cd = parse_timespan_to_seconds(cfg.as_str('cooldown', '6h'))

        self._cd_bitrig = CooldownBiTrigger(deps.db, 'PriceDivergence', self.main_cd, self.main_cd, default=False)
        self.time_series = TimeSeries('PriceDivergence', deps.db, self.MAX_POINTS)

    async def on_data(self, sender, rune_market_info: RuneMarketInfo):
        cex_price, native_price = rune_market_info.cex_price, rune_market_info.pool_rune_price

        if native_price == 0:
            return

        div_p = rune_market_info.divergence_percent

        if div_p < self.min_percent:
            if await self._cd_bitrig.turn_off():
                await self._notify(rune_market_info, below_min_divergence=True)
        elif div_p > self.max_percent:
            if await self._cd_bitrig.turn_on():
                await self._notify(rune_market_info, below_min_divergence=False)

        await self.time_series.add(
            abs_delta=(cex_price - native_price),
            rel_delta=div_p
        )
        # await self.time_series.trim_oldest(self.MAX_POINTS)

    async def _notify(self, rune_market_info: RuneMarketInfo, below_min_divergence):
        if not rune_market_info or not rune_market_info.cex_price:
            self.logger.error('No price info / cex price!')
            return 
        
        await self.pass_data_to_listeners(AlertPriceDiverge(
            rune_market_info,
            below_min_divergence
        ))
