import logging
from typing import List

from localization import LocalizationManager
from services.config import Config
from services.fetch.tx import StakeTxFetcher
from services.models.tx import StakeTx
from services.notify.broadcast import Broadcaster


class StakeTxNotifier(StakeTxFetcher):
    THRESHOLD_RATIO = 5.0
    MAX_ITEMS = 5

    def __init__(self, cfg: Config, broadcaster: Broadcaster, locman: LocalizationManager):
        super().__init__(cfg, broadcaster.db)
        self.broadcaster = broadcaster
        self.loc_man = locman

    async def on_new_txs(self, txs: List[StakeTx]):
        ...

    async def notify_new_tx(self):
        async def message_gen(chat_id):
            loc = await self.loc_man.get_from_db(chat_id, self.db)
            return 'todo'

        users = await self.broadcaster.all_users()
        await self.broadcaster.broadcast(users, message_gen)
