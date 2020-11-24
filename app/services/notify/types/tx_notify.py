import logging
import time
from typing import List

from services.fetch.base import INotified
from services.fetch.tx import StakeTxFetcher
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo, MIDGARD_MULT
from services.models.tx import StakeTx, StakePoolStats


class StakeTxNotifier(INotified):
    MAX_TX_PER_ONE_TIME = 10

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger('StakeTxNotifier')

        scfg = deps.cfg.tx.stake_unstake
        self.min_pool_percent = float(scfg.min_pool_percent)
        self.max_age_sec = parse_timespan_to_seconds(scfg.max_age_sec)
        self.min_usd_total = int(scfg.min_usd_total)

    async def on_data(self, fetcher: StakeTxFetcher, txs: List[StakeTx]):
        new_txs = self._filter_by_age(txs)

        usd_per_rune = self.deps.price_holder.usd_per_rune
        min_rune_volume = self.min_usd_total / usd_per_rune

        large_txs = self._filter_large_txs(fetcher, new_txs, self.min_pool_percent, min_rune_volume)

        large_txs = list(large_txs)
        large_txs = large_txs[:self.MAX_TX_PER_ONE_TIME]

        self.logger.info(f"large_txs: {len(large_txs)}")

        if large_txs:
            user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)

            async def message_gen(chat_id):
                loc = user_lang_map[chat_id]
                texts = []
                for tx in large_txs:
                    pool = fetcher.pool_stat_map.get(tx.pool)
                    pool_info = fetcher.pool_info_map.get(tx.pool)
                    texts.append(loc.notification_text_large_tx(tx, usd_per_rune, pool, pool_info))
                return '\n\n'.join(texts)

            await self.deps.broadcaster.broadcast(user_lang_map.keys(), message_gen)

    def _filter_by_age(self, txs: List[StakeTx]):
        now = int(time.time())
        for tx in txs:
            if tx.date > now - self.max_age_sec:
                yield tx

    @staticmethod
    def _filter_large_txs(fetcher, txs, min_pool_percent=0.5, min_rune_volume=10000):
        for tx in txs:
            tx: StakeTx
            stats: StakePoolStats = fetcher.pool_stat_map.get(tx.pool)
            pool_info: PoolInfo = fetcher.pool_info_map.get(tx.pool)
            min_share_rune_volume = (pool_info.balance_rune * MIDGARD_MULT) * min_pool_percent / 100.0
            if stats is not None:
                if tx.full_rune >= min_rune_volume and tx.full_rune >= min_share_rune_volume:
                    yield tx
