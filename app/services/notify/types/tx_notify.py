from typing import List

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.config import SubConfig
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import linear_transform, class_logger
from services.models.tx import ThorTxExtended, ThorTxType
from services.notify.types.cap_notify import LiquidityCapNotifier


class GenericTxNotifier(INotified):
    DEFAULT_TX_VS_DEPTH_CURVE = [
        {'depth': 10_000, 'percent': 20},  # if depth < 10_000 then 0.2
        {'depth': 100_000, 'percent': 12},  # if 10_000 <= depth < 100_000 then 0.2 ... 0.12
        {'depth': 500_000, 'percent': 8},  # if 100_000 <= depth < 500_000 then 0.12 ... 0.08
        {'depth': 1_000_000, 'percent': 5},  # and so on...
        {'depth': 10_000_000, 'percent': 1.5},
    ]

    @staticmethod
    def curve_for_tx_threshold(curve, depth):
        curve = curve or GenericTxNotifier.DEFAULT_TX_VS_DEPTH_CURVE
        lower_bound = 0
        lower_percent = curve[0]['percent']
        for curve_entry in curve:
            upper_bound = curve_entry['depth']
            upper_percent = curve_entry['percent']
            if depth < upper_bound:
                return linear_transform(depth, lower_bound, upper_bound, lower_percent, upper_percent)
            lower_percent = upper_percent
            lower_bound = upper_bound
        return curve[-1]['percent']

    def __init__(self, deps: DepContainer, params: SubConfig, tx_types):
        self.deps = deps
        self.params = params
        self.tx_types = tx_types
        self.logger = class_logger(self)
        self.max_tx_per_single_message = deps.cfg.as_int('tx.max_tx_per_single_message', 5)

        self.max_age_sec = parse_timespan_to_seconds(deps.cfg.tx.max_age)
        self.min_usd_total = int(params.min_usd_total)

        self.curve = params.get_pure('usd_requirements_curve', self.DEFAULT_TX_VS_DEPTH_CURVE)

    async def on_data(self, senders, txs: List[ThorTxExtended]):
        txs = [tx for tx in txs if tx.type in self.tx_types]  # filter my TX types

        if not txs:
            return

        usd_per_rune = self.deps.price_holder.usd_per_rune

        if not usd_per_rune:
            self.logger.error(f'Can not filter Txs, no USD/Rune price')
            return

        min_rune_volume = self.min_usd_total / usd_per_rune

        large_txs = list(self._filter_large_txs(txs, min_rune_volume, usd_per_rune))
        large_txs = large_txs[:self.max_tx_per_single_message]  # limit for 1 notification

        if not large_txs:
            return
        self.logger.info(f"large_txs: {len(large_txs)}")

        if large_txs:
            cap_info = await LiquidityCapNotifier(self.deps).get_last_cap()

            async def message_gen(loc: BaseLocalization):
                texts = []
                has_liquidity = False
                for tx in large_txs:
                    if tx.type in (ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_ADD_LIQUIDITY):
                        has_liquidity = True
                    pool_info = self.deps.price_holder.pool_info_map.get(tx.first_pool)

                    # append it only to the last one (if has liquidity change TXS)
                    cap_info_last = cap_info if (tx == large_txs[-1] and has_liquidity) else None

                    texts.append(loc.notification_text_large_tx(tx, usd_per_rune, pool_info, cap_info_last))
                return '\n\n'.join(texts)

            await self.deps.broadcaster.notify_preconfigured_channels(message_gen)

    def _get_min_usd_depth(self, tx: ThorTxExtended, usd_per_rune):
        # todo: bugfix! No pool depth for Tx (convert Synth name!!)
        pools = tx.pools or [tx.first_input_tx.first_asset]
        pool_info_list = list(filter(bool, (self.deps.price_holder.pool_info_map.get(pool) for pool in pools)))
        if not pool_info_list:
            return 0.0
        min_pool_depth = min(p.usd_depth(usd_per_rune) for p in pool_info_list)
        return min_pool_depth

    def _filter_large_txs(self, txs, min_rune_volume, usd_per_rune):
        for tx in txs:
            tx: ThorTxExtended

            pool_usd_depth = self._get_min_usd_depth(tx, usd_per_rune)
            if pool_usd_depth == 0.0:
                self.logger.warning(f'No pool depth for Tx: {tx}.')
                min_share_rune_volume = 0.0
            else:
                min_pool_percent = self.curve_for_tx_threshold(self.curve, pool_usd_depth)
                min_share_rune_volume = pool_usd_depth / usd_per_rune * min_pool_percent * 0.01

            if tx.full_rune >= min_rune_volume and tx.full_rune >= min_share_rune_volume:
                yield tx


class SwitchTxNotifier(GenericTxNotifier):
    def _filter_large_txs(self, txs, min_rune_volume, usd_per_rune):
        for tx in txs:
            tx: ThorTxExtended
            if tx.full_rune >= min_rune_volume:
                yield tx
