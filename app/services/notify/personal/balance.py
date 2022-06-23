import asyncio
from typing import List

from localization.base import BaseLocalization
from services.lib.db import DB
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.settings_manager import SettingsManager
from services.models.node_watchers import UserWatchlist
from services.models.transfer import RuneTransfer
from services.notify.channel import ChannelDescriptor, BoardMessage


class WalletWatchlist(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, 'Wallet')

    async def set_user_to_node(self, user_id, node: str, value: bool):
        print(f'{user_id = }, address = {node}: {"ON" if value else "OFF"}')
        return await super().set_user_to_node(user_id, node, value)


class PersonalBalanceNotifier(INotified):
    def __init__(self, d: DepContainer):
        self.deps = d
        self._watcher = WalletWatchlist(d.db)

    async def on_data(self, sender, transfers: List[RuneTransfer]):
        # for tr in transfers:
        #     print(tr)
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
    def __init__(self, mapping: WalletWatchlist):
        self.mapping = mapping

    async def on_data(self, sender: SettingsManager, data):
        #        channel_id, settings = data
        pass
