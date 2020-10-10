import time
from typing import List

from localization import LocalizationManager
from services.config import Config, DB
from services.fetch.tx import StakeTxFetcher
from services.models.tx import StakeTx
from services.notify.broadcast import Broadcaster


class StakeTxNotifier(StakeTxFetcher):
    MAX_TX_PER_ONE_TIME = 10

    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, locman: LocalizationManager):
        super().__init__(cfg, db)
        self.broadcaster = broadcaster
        self.loc_man = locman

        scfg = cfg.tx.stake_unstake
        self.threshold_mult = float(scfg.threshold_mult)
        self.avg_n = int(scfg.avg_n)
        self.max_age_sec = int(scfg.max_age_sec)

    def _filter_by_age(self, txs: List[StakeTx]):
        now = int(time.time())
        for tx in txs:
            if tx.date > now - self.max_age_sec:
                yield tx

    async def on_new_txs(self, txs: List[StakeTx], runes_per_dollar):
        users = await self.broadcaster.all_users()

        new_txs = self._filter_by_age(txs)
        large_txs = self.filter_large_txs(new_txs, self.threshold_mult)

        large_txs = list(large_txs)
        large_txs = large_txs[:self.MAX_TX_PER_ONE_TIME]

        if large_txs:
            await self.broadcaster.broadcast(users, self.localize,
                                             txs=large_txs,
                                             runes_per_dollar=runes_per_dollar)

    async def localize(self, chat_id, txs, runes_per_dollar):
        loc = await self.loc_man.get_from_db(chat_id, self.db)
        return '\n\n'.join(loc.tx_text(tx, runes_per_dollar) for tx in txs)
