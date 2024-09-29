from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.price import RuneMarketInfo


class SupplyNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cd_period = parse_timespan_to_seconds(self.deps.cfg.as_str('supply.period', '7d'))
        self._cd = Cooldown(self.deps.db, 'SupplyNotifyPublic', cd_period)

    async def on_data(self, sender, market_info: RuneMarketInfo):
        if await self._cd.can_do():
            await self._cd.do()
            await self.pass_data_to_listeners(market_info)
