from localization.eng_base import BaseLocalization
from services.dialog.picture.supply_picture import SupplyPictureGenerator
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, today_str
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.price import RuneMarketInfo
from services.notify.channel import BoardMessage


class SupplyNotifier(INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cd_period = parse_timespan_to_seconds(self.deps.cfg.as_str('supply.period', '7d'))
        self._cd = Cooldown(self.deps.db, 'SupplyNotifyPublic', cd_period)

    async def on_data(self, sender, market_info: RuneMarketInfo):
        if await self._cd.can_do():
            await self._cd.do()
            await self._notify(market_info)

    async def _notify(self, market_info: RuneMarketInfo):
        async def supply_pic_gen(loc: BaseLocalization):
            gen = SupplyPictureGenerator(loc, market_info.supply_info, self.deps.killed_rune, self.deps.net_stats)
            pic = await gen.get_picture()
            return BoardMessage.make_photo(pic, loc.SUPPLY_PIC_CAPTION, f'rune_supply_{today_str()}.png')

        await self.deps.broadcaster.notify_preconfigured_channels(BaseLocalization.text_metrics_supply,
                                                                  market_info, self.deps.killed_rune)
        await self.deps.broadcaster.notify_preconfigured_channels(supply_pic_gen)
