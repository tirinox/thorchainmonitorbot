import asyncio

from localization.base import BaseLocalization
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.settings_manager import SettingsManager
from services.models.node_watchers import AlertWatchers
from services.models.transfer import RuneTransfer
from services.notify.channel import ChannelDescriptor, BoardMessage
from services.notify.personal.helpers import GeneralSettings


class PersonalBalanceNotifier(INotified):
    def __init__(self, d: DepContainer):
        self.deps = d

    async def on_data(self, sender, data):
        pass

    async def _send_message(self, channel_info: ChannelDescriptor, transfer: RuneTransfer):
        loc: BaseLocalization = await self.deps.loc_man.get_from_lang(channel_info.lang)

        text = loc.notification_text_rune_transfer(transfer)
        task = self.deps.broadcaster.safe_send_message_rate(
            channel_info,
            BoardMessage(text)
        )
        asyncio.create_task(task)


class SettingsProcessorBalanceTracker(INotified):
    def __init__(self, alert_watcher: AlertWatchers):
        self.alert_watcher = alert_watcher

    async def on_data(self, sender: SettingsManager, data):
        channel_id, settings = data
        is_enabled = settings.get(GeneralSettings.BALANCE_TRACK, False)
        # todo!
        await self.alert_watcher.set_user_to_node(channel_id, GeneralSettings.BALANCE_TRACK, is_enabled)
