import logging
import time
from typing import List, Dict

from localization import LocalizationManager
from services.config import Config, DB
from services.fetch.tx import StakeTxFetcher
from services.models.tx import StakeTx, StakePoolStats
from services.notify.broadcast import Broadcaster, telegram_chats_from_config


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

    async def on_new_txs(self, txs: List[StakeTx]):
        new_txs = self._filter_by_age(txs)
        large_txs = self.filter_large_txs(new_txs, self.threshold_mult)

        large_txs = list(large_txs)
        large_txs = large_txs[:self.MAX_TX_PER_ONE_TIME]

        logging.info(f"large_txs: {len(large_txs)}")

        if large_txs:
            runes_per_dollar = self.runes_per_dollar
            user_lang_map = telegram_chats_from_config(self.cfg, self.loc_man)

            async def message_gen(chat_id):
                loc = user_lang_map[chat_id]
                texts = []
                for tx in large_txs:
                    pool = self.pool_stat_map.get(tx.pool)
                    texts.append(loc.tx_text(tx, runes_per_dollar, pool))
                return '\n\n'.join(texts)

            await self.broadcaster.broadcast(user_lang_map.keys(), message_gen)
