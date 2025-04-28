import json
from typing import Optional

from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.circ_supply import RuneCirculatingSupply
from models.price import RuneMarketInfo


class SupplyNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cd_period = parse_timespan_to_seconds(self.deps.cfg.as_str('supply.notification.period', '7d'))
        self._cd = Cooldown(self.deps.db, 'SupplyNotifyPublic', cd_period)

    DB_KEY_SUPPLY = 'RuneSupply:last'

    async def _save_state(self, supply_info: RuneCirculatingSupply):
        if not supply_info:
            return
        r = await self.deps.db.get_redis()
        await r.set(self.DB_KEY_SUPPLY, json.dumps(supply_info.to_dict()))

    async def _load_state(self) -> Optional[RuneCirculatingSupply]:
        try:
            r = await self.deps.db.get_redis()
            if data := await r.get(self.DB_KEY_SUPPLY):
                return RuneCirculatingSupply.from_dict(json.loads(data))
        except Exception as e:
            self.logger.error(f'Failed to load supply info from DB: {e}')

    async def on_data(self, sender, market_info: RuneMarketInfo):
        if not market_info or not (supply := market_info.supply_info):
            self.logger.error(f'Market Info is incomplete: {market_info = }. Ignoring!')
            return

        if not supply.bonded or not supply.pooled:
            self.logger.error(f'Supply Info is incomplete: {supply.pooled = }, {supply.bonded = }. Ignoring!')
            return

        if await self._cd.can_do():
            last_supply = await self._load_state()
            market_info.prev_supply_info = last_supply
            await self.pass_data_to_listeners(market_info)
            await self._save_state(supply)
            await self._cd.do()
