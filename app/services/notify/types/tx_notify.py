import logging
import time
from typing import List

from services.jobs.fetch.base import INotified
from services.jobs.fetch.tx import TxFetcher
from services.jobs.pool_stats import PoolStatsUpdater
from services.lib.config import SubConfig
from services.lib.constants import THOR_DIVIDER_INV
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import linear_transform
from services.models.pool_info import PoolInfo
from services.models.pool_stats import LiquidityPoolStats
from services.models.tx import LPAddWithdrawTx
from services.notify.types.cap_notify import LiquidityCapNotifier


class PoolLiquidityTxNotifier(INotified):
    MAX_TX_PER_ONE_TIME = 12

    DEFAULT_TX_VS_DEPTH_CURVE = [
        {'depth': 10_000, 'percent': 20},  # if depth < 10_000 then 0.2
        {'depth': 100_000, 'percent': 12},  # if 10_000 <= depth < 100_000 then 0.2 ... 0.12
        {'depth': 500_000, 'percent': 8},  # if 100_000 <= depth < 500_000 then 0.12 ... 0.08
        {'depth': 1_000_000, 'percent': 5},  # and so on...
        {'depth': 10_000_000, 'percent': 1.5},
    ]

    def curve_for_tx_threshold(self, depth):
        lower_bound = 0
        lower_percent = self.curve[0]['percent']
        for curve_entry in self.curve:
            upper_bound = curve_entry['depth']
            upper_percent = curve_entry['percent']
            if depth < upper_bound:
                return linear_transform(depth, lower_bound, upper_bound, lower_percent, upper_percent)
            lower_percent = upper_percent
            lower_bound = upper_bound
        return self.curve[-1]['percent']

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)

        scfg: SubConfig = deps.cfg.tx.liquidity
        self.max_age_sec = parse_timespan_to_seconds(scfg.max_age)
        self.min_usd_total = int(scfg.min_usd_total)

        self.curve = scfg.get_pure('usd_requirements_curve', None)
        if not self.curve:
            self.curve = self.DEFAULT_TX_VS_DEPTH_CURVE

    async def on_data(self, senders, txs: List[LPAddWithdrawTx]):
        fetcher: TxFetcher = senders[0]
        psu: PoolStatsUpdater = senders[1]

        new_txs = self._filter_by_age(txs)

        usd_per_rune = self.deps.price_holder.usd_per_rune
        min_rune_volume = self.min_usd_total / usd_per_rune

        large_txs = list(self._filter_large_txs(psu, new_txs, min_rune_volume))
        large_txs = large_txs[:self.MAX_TX_PER_ONE_TIME]  # limit for 1 notification

        self.logger.info(f"large_txs: {len(large_txs)}")

        if large_txs:
            user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)

            cap_info = await LiquidityCapNotifier(self.deps).get_old_cap()

            async def message_gen(chat_id):
                loc = user_lang_map[chat_id]
                texts = []
                for tx in large_txs:
                    pool_info = self.deps.price_holder.pool_info_map.get(tx.pool)
                    cap_info_last = cap_info if tx == large_txs[-1] else None  # append it only to the last one
                    texts.append(loc.notification_text_large_tx(tx, usd_per_rune, pool_info, cap_info_last))
                return '\n\n'.join(texts)

            await self.deps.broadcaster.broadcast(user_lang_map.keys(), message_gen)

        hashes = [t.tx.tx_hash for t in txs]
        await fetcher.add_last_seen_tx_hashes(hashes)

    def _filter_by_age(self, txs: List[LPAddWithdrawTx]):
        now = int(time.time())
        for tx in txs:
            if tx.date > now - self.max_age_sec:
                yield tx

    def _filter_large_txs(self, psu: PoolStatsUpdater, txs, min_rune_volume=10000):
        price_holder = psu.deps.price_holder

        for tx in txs:
            tx: LPAddWithdrawTx
            stats: LiquidityPoolStats = psu.pool_stat_map.get(tx.pool)
            pool_info: PoolInfo = price_holder.pool_info_map.get(tx.pool)

            if not stats or not pool_info:
                continue

            usd_depth = pool_info.usd_depth(price_holder.usd_per_rune)
            min_pool_percent = self.curve_for_tx_threshold(usd_depth)
            min_share_rune_volume = (2 * pool_info.balance_rune * THOR_DIVIDER_INV) * min_pool_percent * 0.01

            # print(f"{tx.pool}: {tx.full_rune:.2f} / {min_share_rune_volume:.2f} need rune,
            # min_pool_percent = {min_pool_percent:.2f}, "
            #       f"usd_depth = {usd_depth:.0f}")

            if stats is not None:
                if tx.full_rune >= min_rune_volume and tx.full_rune >= min_share_rune_volume:
                    yield tx
