import time
from typing import List

from localization import LocalizationManager
from services.config import Config, DB
from services.fetch.tx import StakeTxFetcher
from services.models.tx import StakeTx
from services.notify.broadcast import Broadcaster


class StakeTxNotifier(StakeTxFetcher):
    THRESHOLD_RATIO = 5  # times
    MAX_ITEMS = 5
    MAX_AGE = 60 * 10  # sec

    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, locman: LocalizationManager):
        super().__init__(cfg, db)
        self.broadcaster = broadcaster
        self.loc_man = locman

    def _filter_by_age(self, txs: List[StakeTx]):
        now = int(time.time())
        for tx in txs:
            if tx.date > now - self.MAX_AGE:
                yield tx

    async def on_new_txs(self, txs: List[StakeTx], runes_per_dollar):
        users = await self.broadcaster.all_users()

        new_txs = self._filter_by_age(txs)
        large_txs = self.filter_small_txs(new_txs, self.THRESHOLD_RATIO)

        large_txs = list(large_txs)
        large_txs = large_txs[:self.MAX_ITEMS]

        if large_txs:
            await self.broadcaster.broadcast(users, self.localize, txs=large_txs, runes_per_dollar=runes_per_dollar)

    async def localize(self, chat_id, txs, runes_per_dollar):
        loc = await self.loc_man.get_from_db(chat_id, self.db)
        return '\n\n'.join(loc.tx_text(tx, runes_per_dollar) for tx in txs)
