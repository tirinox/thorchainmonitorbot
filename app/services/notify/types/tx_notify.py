import logging
import time
from typing import List

from services.jobs.fetch.base import INotified
from services.jobs.fetch.tx import TxFetcher
from services.jobs.pool_stats import PoolStatsUpdater
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.tx import StakeTx
from services.models.pool_stats import StakePoolStats


class StakeTxNotifier(INotified):
    MAX_TX_PER_ONE_TIME = 10

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger('StakeTxNotifier')

        scfg = deps.cfg.tx.stake_unstake
        self.min_pool_percent = float(scfg.min_pool_percent)
        self.max_age_sec = parse_timespan_to_seconds(scfg.max_age)
        self.min_usd_total = int(scfg.min_usd_total)

    async def on_data(self, senders, txs: List[StakeTx]):
        fetcher: TxFetcher = senders[0]
        psu: PoolStatsUpdater = senders[1]

        new_txs = self._filter_by_age(txs)

        usd_per_rune = self.deps.price_holder.usd_per_rune
        min_rune_volume = self.min_usd_total / usd_per_rune

        large_txs = list(self._filter_large_txs(psu, new_txs, min_rune_volume))
        large_txs = large_txs[:self.MAX_TX_PER_ONE_TIME]

        self.logger.info(f"large_txs: {len(large_txs)}")

        if large_txs:
            user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)

            async def message_gen(chat_id):
                loc = user_lang_map[chat_id]
                texts = []
                for tx in large_txs:
                    pool = psu.pool_stat_map.get(tx.pool)
                    pool_info = psu.pool_info_map.get(tx.pool)
                    texts.append(loc.notification_text_large_tx(tx, usd_per_rune, pool, pool_info))
                return '\n\n'.join(texts)

            await self.deps.broadcaster.broadcast(user_lang_map.keys(), message_gen)

        hashes = [t.tx.tx_hash for t in txs]
        await fetcher.add_last_seen_tx_hashes(hashes)

    def _filter_by_age(self, txs: List[StakeTx]):
        now = int(time.time())
        for tx in txs:
            if tx.date > now - self.max_age_sec:
                yield tx

    @staticmethod
    def _filter_large_txs(psu: PoolStatsUpdater, txs, min_rune_volume=10000):
        for tx in txs:
            tx: StakeTx
            stats: StakePoolStats = psu.pool_stat_map.get(tx.pool)
            pool_info: PoolInfo = psu.pool_info_map.get(tx.pool)

            if not stats or not pool_info:
                continue

            usd_depth = pool_info.usd_depth(psu.deps.price_holder.usd_per_rune)
            min_pool_percent = stats.curve_for_tx_threshold(usd_depth)
            min_share_rune_volume = (pool_info.balance_rune * THOR_DIVIDER_INV) * min_pool_percent

            # print(f"{tx.pool}: {tx.full_rune:.2f} / {min_share_rune_volume:.2f} need rune,
            # min_pool_percent = {min_pool_percent:.2f}, "
            #       f"usd_depth = {usd_depth:.0f}")

            if stats is not None:
                if tx.full_rune >= min_rune_volume and tx.full_rune >= min_share_rune_volume:
                    yield tx
