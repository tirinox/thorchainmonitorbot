from services.lib.delegates import INotified
from services.lib.settings_manager import SettingsManager
from services.models.node_watchers import AlertWatchers
from services.notify.personal.helpers import GeneralSettings


class SettingsProcessorBalanceTracker(INotified):
    def __init__(self, alert_watcher: AlertWatchers):
        self.alert_watcher = alert_watcher

    async def on_data(self, sender: SettingsManager, data):
        channel_id, settings = data
        is_enabled = settings.get(GeneralSettings.BALANCE_TRACK, False)
        # todo!
        await self.alert_watcher.set_user_to_node(channel_id, GeneralSettings.BALANCE_TRACK, is_enabled)
