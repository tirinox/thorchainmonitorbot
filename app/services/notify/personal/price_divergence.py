import asyncio

from localization import LocalizationManager
from services.jobs.fetch.base import INotified
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.price import RuneMarketInfo
from services.notify.channel import ChannelDescriptor, BoardMessage, Messengers
from services.notify.personal.helpers import GeneralSettings


class PersonalPriceDivergenceNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.personal_cooldown = parse_timespan_to_seconds(
            deps.cfg.as_str('price.divergence.personal.cooldown', '1h')
        )
        self.logger = class_logger(self)

    async def remove_user_from_watchers(self, user_id):
        ...

    async def add_user_to_watchers(self, user_id):
        ...

    async def on_data(self, sender, rune_market_info: RuneMarketInfo):
        # todo!
        users = await self.deps.settings_manager.alert_watcher.all_users_for_node(
            GeneralSettings.SETTINGS_KEY_PRICE_DIV_ALERTS)
        pass
        """
        1. get all watchers
        2. compare with their settings
        3. check for bi trigger and cooldown
        4. send notifications
        """
        # await self._dbg_test(rune_market_info)

    async def _dbg_test(self, rune_market_info: RuneMarketInfo):
        loc_man: LocalizationManager = self.deps.loc_man

        text = loc_man.default.notification_text_price_divergence(rune_market_info, normal=False)

        task = self.deps.broadcaster.safe_send_message(
            ChannelDescriptor(Messengers.TELEGRAM, '192398802'),
            BoardMessage(text)
        )
        asyncio.create_task(task)
